import asyncio
import json
import multiprocessing
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from broker.durability import Journal, publish, read_request
from broker.main import Broker
from broker.protocol import make_response


def raw(identity='durable-id', content='fixture'):
    return json.dumps(dict(request_id=identity, model='fast', messages=[dict(role='user', content=content)])).encode()


def broker_at(root):
    config = SimpleNamespace(**{'rpc_'+name+'_dir': str(root/name) for name in ('in', 'out', 'failed')}, max_queue_size=8)
    with patch('broker.main.load_config', return_value=config):
        broker = Broker()
    broker._process_request_with_litellm = AsyncMock(return_value=make_response('durable-id', content='fixture result'))
    return broker


def submit(root, content=None):
    (root/'in/req-durable-id.json').write_bytes(raw() if content is None else content)


def test_consumed_response_republished_after_restart_without_inference(tmp_path):
    first = broker_at(tmp_path); submit(tmp_path)
    asyncio.run(first._process_requests())
    response = tmp_path/'out/resp-durable-id.json'
    saved = response.read_bytes(); response.unlink()
    restarted = broker_at(tmp_path); submit(tmp_path)
    asyncio.run(restarted._process_requests())
    restarted._process_request_with_litellm.assert_not_called()
    assert response.read_bytes() == saved


def test_changed_payload_never_reuses_identity(tmp_path):
    first = broker_at(tmp_path); submit(tmp_path)
    asyncio.run(first._process_requests())
    (tmp_path/'out/resp-durable-id.json').unlink()
    restarted = broker_at(tmp_path); submit(tmp_path, raw(content='different'))
    asyncio.run(restarted._process_requests())
    restarted._process_request_with_litellm.assert_not_called()
    assert not (tmp_path/'out/resp-durable-id.json').exists()


@pytest.mark.parametrize('state', ['CLAIMED', 'UNCERTAIN'])
def test_crash_claim_never_retries(tmp_path, state):
    broker = broker_at(tmp_path)
    with Journal(tmp_path/'failed/.broker-state') as journal:
        journal.claim('durable-id', raw())
        if state == 'UNCERTAIN': journal.uncertain('durable-id')
    submit(tmp_path); asyncio.run(broker._process_requests())
    broker._process_request_with_litellm.assert_not_called()
    result = json.loads((tmp_path/'out/resp-durable-id.json').read_bytes())
    assert result['ok'] is False and 'uncertain' in result['error']


def test_publish_failure_replays_cached_response(tmp_path):
    broker = broker_at(tmp_path); submit(tmp_path)
    with patch('broker.main.publish', side_effect=OSError('fixture disk failure')):
        asyncio.run(broker._process_requests())
    broker._process_request_with_litellm.assert_awaited_once()
    restarted = broker_at(tmp_path); submit(tmp_path)
    asyncio.run(restarted._process_requests())
    restarted._process_request_with_litellm.assert_not_called()
    assert json.loads((tmp_path/'out/resp-durable-id.json').read_bytes())['ok'] is True


def test_inference_exception_is_not_retried_and_releases_budget(tmp_path):
    broker = broker_at(tmp_path); submit(tmp_path)
    broker._process_request_with_litellm.side_effect = RuntimeError('private failure')
    asyncio.run(broker._process_requests())
    restarted = broker_at(tmp_path); submit(tmp_path)
    asyncio.run(restarted._process_requests())
    restarted._process_request_with_litellm.assert_not_called()


def test_cancelled_task_keeps_uncertain_claim(tmp_path):
    broker = broker_at(tmp_path); submit(tmp_path)
    broker._process_request_with_litellm.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError): asyncio.run(broker._process_requests())
    restarted = broker_at(tmp_path); submit(tmp_path)
    asyncio.run(restarted._process_requests())
    restarted._process_request_with_litellm.assert_not_called()


@pytest.mark.parametrize('kind', ['symlink', 'hardlink', 'fifo', 'directory', 'oversize'])
def test_unsafe_request_nodes_never_reach_inference(tmp_path, kind):
    broker = broker_at(tmp_path)
    target = tmp_path/'in/req-durable-id.json'
    external = tmp_path/'external'; external.write_bytes(raw())
    if kind == 'symlink': target.symlink_to(external)
    elif kind == 'hardlink': os.link(external, target)
    elif kind == 'fifo': os.mkfifo(target)
    elif kind == 'directory': target.mkdir()
    else: target.write_bytes(b'x'*65537)
    asyncio.run(broker._process_requests())
    broker._process_request_with_litellm.assert_not_called()
    assert external.read_bytes() == raw()


def test_existing_response_symlink_not_followed(tmp_path):
    broker = broker_at(tmp_path); submit(tmp_path)
    victim = tmp_path/'victim'; victim.write_text('preserved')
    (tmp_path/'out/resp-durable-id.json').symlink_to(victim)
    asyncio.run(broker._process_requests())
    broker._process_request_with_litellm.assert_not_called()
    assert victim.read_text() == 'preserved'


def test_atomic_publish_never_overwrites(tmp_path):
    target = tmp_path/'response'
    publish(target, b'first')
    with pytest.raises(FileExistsError): publish(target, b'second')
    assert target.read_bytes() == b'first'
    assert not list(tmp_path.glob('.response-*'))


def test_journal_lock_excludes_other_instance(tmp_path):
    with Journal(tmp_path/'state'):
        with pytest.raises(BlockingIOError):
            with Journal(tmp_path/'state'): pass


def test_private_journal_required(tmp_path):
    state=tmp_path/'state'; state.mkdir(mode=0o755)
    with pytest.raises(ValueError):
        with Journal(state): pass


def process_worker(root):
    root = Path(root)
    broker = broker_at(root)
    async def fake(request):
        with (root/'calls').open('a') as output: output.write('call\n')
        await asyncio.sleep(.1)
        return make_response(request.request_id, content='mock')
    broker._process_request_with_litellm = fake
    asyncio.run(broker._process_requests())


def test_two_processes_never_duplicate_inference(tmp_path):
    broker_at(tmp_path); submit(tmp_path)
    ctx = multiprocessing.get_context('fork')
    workers = [ctx.Process(target=process_worker, args=(str(tmp_path),)) for _ in range(2)]
    for worker in workers: worker.start()
    for worker in workers:
        worker.join(5)
        assert worker.exitcode == 0
    assert (tmp_path/'calls').read_text() == 'call\n'


def test_corrupt_journal_fails_before_inference(tmp_path):
    broker = broker_at(tmp_path); submit(tmp_path)
    state = tmp_path/'failed/.broker-state'; state.mkdir(mode=0o700)
    (state/'requests.sqlite').write_bytes(b'invalid sqlite')
    with pytest.raises(Exception): asyncio.run(broker._process_requests())
    broker._process_request_with_litellm.assert_not_called()
    assert (tmp_path/'in/req-durable-id.json').exists()


def crash_after_model(root):
    broker = broker_at(Path(root))
    async def fake(request):
        (Path(root)/'model-called').write_text('mock only')
        os._exit(17)  # process crash before journal completion/publication
    broker._process_request_with_litellm = fake
    asyncio.run(broker._process_requests())


def test_actual_process_crash_before_completion_stays_uncertain(tmp_path):
    broker_at(tmp_path); submit(tmp_path)
    worker=multiprocessing.get_context('fork').Process(target=crash_after_model,args=(str(tmp_path),))
    worker.start();worker.join(5)
    assert worker.exitcode == 17
    assert (tmp_path/'model-called').exists()
    restarted=broker_at(tmp_path);submit(tmp_path)
    asyncio.run(restarted._process_requests())
    restarted._process_request_with_litellm.assert_not_called()
    assert 'uncertain' in json.loads((tmp_path/'out/resp-durable-id.json').read_bytes())['error']


def test_batch_limit_preserved(tmp_path):
    broker=broker_at(tmp_path)
    broker.config.max_queue_size=2
    for n in range(3): (tmp_path/('in/req-id%d.json'%n)).write_bytes(raw(identity='id%d'%n))
    asyncio.run(broker._process_requests())
    assert broker._process_request_with_litellm.await_count == 2
    assert len(list((tmp_path/'in').glob('req-*.json'))) == 1


def test_symlink_swap_at_open_cannot_escape(tmp_path):
    target=tmp_path/'request';target.write_bytes(raw())
    victim=tmp_path/'victim';victim.write_bytes(b'private content')
    original=os.open
    def swapped(path, flags, *args, **kwargs):
        target.unlink();target.symlink_to(victim)
        return original(path,flags,*args,**kwargs)
    with patch('broker.durability.os.open',side_effect=swapped), pytest.raises(OSError): read_request(target)
    assert victim.read_bytes() == b'private content'
