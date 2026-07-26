import Database from 'better-sqlite3';
const db = new Database('data/v2.db');
console.log(db.prepare('SELECT id FROM agent_groups').all());
