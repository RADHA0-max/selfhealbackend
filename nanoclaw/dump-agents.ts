import Database from 'better-sqlite3';
const db = new Database('data/v2.db');

console.log('--- AGENT GROUPS ---');
console.log(db.prepare("SELECT * FROM agent_groups").all());
console.log('--- CONTAINER CONFIGS ---');
console.log(db.prepare("SELECT agent_group_id, provider, model FROM container_configs").all());
