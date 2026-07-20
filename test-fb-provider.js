require('dotenv').config({path: '.env'});
require('ts-node').register({ transpileOnly: true });

const { FacebookProvider } = require('./libraries/nestjs-libraries/src/integrations/social/facebook.provider.ts');

async function test() {
  const provider = new FacebookProvider();
  const res = await provider.generateAuthUrl();
  console.log('FACEBOOK_APP_ID:', process.env.FACEBOOK_APP_ID);
  console.log('URL:', res.url);
}

test().catch(console.error);
