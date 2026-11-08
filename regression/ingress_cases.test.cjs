const { test } = require('node:test'), assert=require('node:assert/strict');
const https=require('node:https'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),{execFileSync}=require('node:child_process');
const {strictMismatch,certificateAt}=require('./ingress_cases.cjs');
test('strict certificate mismatch rejects an incomplete real chain before any application HTTP request',async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'regression-ingress-test-'));let calls=0,server;
 try{
  const key=path.join(root,'key.pem'),cert=path.join(root,'cert.pem');
  const caKey=path.join(root,'ca-key.pem'),caCert=path.join(root,'ca.pem'),csr=path.join(root,'leaf.csr'),ext=path.join(root,'leaf.ext');
  execFileSync('openssl',['req','-x509','-newkey','rsa:2048','-nodes','-keyout',caKey,'-out',caCert,'-subj','/CN=Regression CA','-days','1'],{stdio:'ignore'});
  execFileSync('openssl',['req','-new','-newkey','rsa:2048','-nodes','-keyout',key,'-out',csr,'-subj','/CN=tenant.test'],{stdio:'ignore'});
  fs.writeFileSync(ext,'subjectAltName=DNS:tenant.test\n');
  execFileSync('openssl',['x509','-req','-in',csr,'-CA',caCert,'-CAkey',caKey,'-CAcreateserial','-out',cert,'-days','1','-extfile',ext],{stdio:'ignore'});
  server=https.createServer({key:fs.readFileSync(key),cert:fs.readFileSync(cert)},(req,res)=>{calls++;res.end('unexpected')});
  await new Promise(r=>server.listen(0,'127.0.0.1',r));const port=server.address().port;
  const observed=await certificateAt('127.0.0.1',port,'tenant.test');assert.ok(observed.raw);
  assert.equal((await strictMismatch('127.0.0.1',port,'wrong.test',fs.readFileSync(cert))).code,'ERR_TLS_CERT_ALTNAME_INVALID');assert.equal(calls,0);
 }finally{if(server)await new Promise(r=>server.close(r));fs.rmSync(root,{recursive:true,force:true})}
});
