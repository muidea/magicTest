// Read-only ingress verification; no routing, certificate or deployment edits.
const tls = require('node:tls');
const https = require('node:https');
const crypto = require('node:crypto');
function certificateAt(host, port, servername) {
 return new Promise((resolve,reject)=>{
  const socket=tls.connect({host,port,servername,rejectUnauthorized:false});
  socket.setTimeout(10000,()=>socket.destroy(Error('Certificate observation timeout')));
  socket.once('error',reject);
  socket.once('secureConnect',()=>{const peer=socket.getPeerCertificate(true);socket.end();if(!peer?.raw)return reject(Error('Actual ingress did not supply a certificate'));resolve(peer)});
 });
}
function strictMismatch(host,port,servername,ca) {
 return new Promise((resolve,reject)=>{
  const request=https.request({hostname:host,port,servername,ca,allowPartialTrustChain:true,rejectUnauthorized:true,method:'GET',path:'/api/v1/web/session/',headers:{Host:servername}},response=>{response.resume();reject(Error('Strict TLS unexpectedly reached an application response'))});
  request.setTimeout(10000,()=>request.destroy(Error('Strict TLS timeout')));
  request.once('error',error=>{if(error.code==='ERR_TLS_CERT_ALTNAME_INVALID')resolve({code:error.code});else reject(error)});
  request.end();
 });
}
async function certificateMismatch(h) {
 const origin=new URL(h.credentials.origin),host=origin.hostname.endsWith('.local.vpc')?'127.0.0.1':origin.hostname,port=Number(origin.port||443);
 const peer=await certificateAt(host,port,origin.hostname),servername='regression-'+crypto.randomBytes(16).toString('hex')+'.invalid';
 const error=tls.checkServerIdentity(servername,peer);
 h.check('Actual ingress certificate does not cover the independent mismatched Host fixture',error?.code==='ERR_TLS_CERT_ALTNAME_INVALID',{certificateFingerprint:peer.fingerprint256,subjectAltName:peer.subjectaltname,fixtureHost:servername});
 // Explicitly trust only the observed chain to isolate name validation from
 // this environment's private CA, whose issuer may be omitted by the server.
 // The observed certificate is an explicit probe-only trust anchor; strict
 // hostname verification stays enabled even for an incomplete chain.
 let root=peer;const seen=new Set();
 while(root.issuerCertificate?.raw&&!seen.has(root.issuerCertificate.fingerprint256)){seen.add(root.fingerprint256);if(root.issuerCertificate.fingerprint256===root.fingerprint256)break;root=root.issuerCertificate;}
 const ca='-----BEGIN CERTIFICATE-----\n'+root.raw.toString('base64').match(/.{1,64}/g).join('\n')+'\n-----END CERTIFICATE-----\n';
 const result=await strictMismatch(host,port,servername,ca);
 h.check('Strict TLS rejects the real mismatched certificate before any application response',result.code==='ERR_TLS_CERT_ALTNAME_INVALID',result);
}
const handlers={'F062-002':async h=>{
 const unknown='missing-'+crypto.randomBytes(12).toString('hex'),origin=new URL(h.credentials.origin);origin.hostname=unknown+'.'+origin.hostname.split('.').slice(1).join('.');
 const namespaces=await h.directory(h.admin,'/cas/namespaces/');
 h.check('Unknown ingress fixture has no current CAS tenant identity',!namespaces.some(n=>n.name===unknown));
 const context=await h.browser.newContext({ignoreHTTPSErrors:true});const actor={context,page:await context.newPage(),origin:origin.origin,identity:{account:'anonymous',namespace:unknown}};
 try{
  const first=await actor.page.goto(actor.origin+'/',{waitUntil:'networkidle'});
  h.check('Unknown Host root does not expose a default-tenant page',first.status()===404,{status:first.status()});
  for(const route of ['/api/v1/web/session/','/api/v1/web/proxy/system/context/?surface=panel','/.well-known/openid-configuration','/api/v1/cas/registration/policy/public/']){
   const response=await h.publicGet(actor,route);
   h.check('Unknown Host cannot obtain a default tenant through '+route,response.status===404&&!response.data?.value?.account&&!response.data?.value?.homeNamespace,response);
  }
  h.check('Unknown Host never establishes a BFF session cookie',!(await context.cookies(actor.origin)).some(c=>c.httpOnly));
  await h.screenshot(actor,'unknown-ingress-host');
 }finally{await context.close()}
 await certificateMismatch(h);
}};
module.exports={handlers,strictMismatch,certificateAt};
