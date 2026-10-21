import os,time,logging,requests
from flask import Flask,request,jsonify,Response
from prometheus_client import Counter,Histogram,generate_latest,CONTENT_TYPE_LATEST
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

NAME=os.getenv('SERVICE_NAME','api'); TOKEN=os.getenv('BENCH_TOKEN','local-benchmark-only'); app=Flask(__name__)
logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
provider=TracerProvider(resource=Resource.create({'service.name':f'selfheal-{NAME}'}))
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=os.getenv('OTEL_EXPORTER_OTLP_TRACES_ENDPOINT','http://otel:4318/v1/traces'))))
trace.set_tracer_provider(provider); FlaskInstrumentor().instrument_app(app); RequestsInstrumentor().instrument()
REQ=Counter('selfheal_requests_total','HTTP requests',['service','route','status'])
LAT=Histogram('selfheal_request_duration_seconds','HTTP request duration',['service','route'])
FAULT={'mode':'none','delay_ms':0}
@app.before_request
def start(): request._started=time.monotonic()
@app.after_request
def observe(resp):
    route='/work' if request.path=='/work' else request.path
    if route not in ('/metrics','/__bench/fault'): REQ.labels(NAME,route,str(resp.status_code)).inc(); LAT.labels(NAME,route).observe(time.monotonic()-request._started)
    return resp
@app.get('/health')
def health(): return jsonify(service=NAME,ok=True)
@app.get('/work')
def work():
    if FAULT['mode']=='error': return jsonify(error='injected failure',service=NAME),503
    if FAULT['mode']=='latency': time.sleep(FAULT['delay_ms']/1000)
    if NAME=='api':
        targets=['http://auth:8080/work','http://worker:8080/work']
    elif NAME=='worker': targets=['http://db:8080/work']
    else: targets=[]
    for target in targets:
        try:
            r=requests.get(target,timeout=2)
            if r.status_code!=200: return jsonify(error='dependency failure',dependency=target),503
        except requests.RequestException: return jsonify(error='dependency unavailable',dependency=target),503
    return jsonify(service=NAME,status='ok')
@app.route('/__bench/fault',methods=['GET','POST'])
def fault():
    if request.headers.get('X-Bench-Token')!=TOKEN: return jsonify(error='unauthorized'),403
    if request.method=='POST':
        body=request.get_json(force=True); mode=body.get('mode','none'); delay=body.get('delay_ms',0)
        if mode not in ('none','error','latency') or not isinstance(delay,int) or not 0<=delay<=3000: return jsonify(error='invalid fault'),400
        FAULT.update(mode=mode,delay_ms=delay)
    return jsonify(service=NAME,**FAULT)
@app.get('/metrics')
def metrics(): return Response(generate_latest(),mimetype=CONTENT_TYPE_LATEST)
if __name__=='__main__': app.run(host='0.0.0.0',port=8080,threaded=True)
