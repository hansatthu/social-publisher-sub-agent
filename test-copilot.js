const fetch = require('node-fetch'); // we can just use native fetch in node 18+

async function testCopilot() {
  try {
    const res = await fetch('http://localhost:3000/copilot/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        messages: [{ role: 'user', content: 'hello' }]
      })
    });
    console.log(res.status);
    const text = await res.text();
    console.log(text.substring(0, 500));
  } catch(e) {
    console.error(e);
  }
}

testCopilot();
