import Database from 'better-sqlite3';
const db = new Database('data/v2.db');

try {
  db.prepare(`
    UPDATE container_configs SET skills = '[]' WHERE agent_group_id = 'devops_agent'
  `).run();
  console.log('✅ Skills set to empty — no symlinks needed!');
} catch (err) {
  console.error('Error:', err);
}
