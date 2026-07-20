const http = require('http');

const data = JSON.stringify({
  messages: [{ role: 'user', content: 'hello' }]
});

const options = {
  hostname: 'localhost',
  port: 3000,
  path: '/copilot/chat',
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Content-Length': Buffer.byteLength(data)
  }
};

const req = http.request(options, res => {
  console.log(`STATUS: ${res.statusCode}`);
  let body = '';
  res.on('data', chunk => body += chunk);
  res.on('end', () => console.log('BODY:', body.substring(0, 1000)));
});

req.on('error', e => console.error(e));
req.write(data);
req.end();
