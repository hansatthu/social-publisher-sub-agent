require('dotenv').config({path: '.env'});

async function testDeepseek() {
  const res = await fetch('https://api.deepseek.com/chat/completions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${process.env.DEEPSEEK_API_KEY}`
    },
    body: JSON.stringify({
      model: 'deepseek-chat',
      messages: [{role: 'user', content: 'hello'}]
    })
  });
  console.log(res.status, await res.text());
}

testDeepseek().catch(console.error);
