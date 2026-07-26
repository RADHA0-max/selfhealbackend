import Database from 'better-sqlite3';
const db = new Database('data/v2.db');
console.log('--- INBOUND ---');
console.log(db.prepare("SELECT * FROM messages_in").all());
console.log('--- DROPPED ---');
console.log(db.prepare("SELECT * FROM dropped_messages").all());
