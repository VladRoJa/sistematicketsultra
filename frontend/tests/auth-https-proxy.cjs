'use strict';
/**
 * Loopback-only HTTPS reverse proxy for CI browser tests.
 * Generated self-signed certificate is temporary and never committed.
 */
const https = require('node:https');
const http = require('node:http');
const fs = require('node:fs');

const server = https.createServer({
  key: fs.readFileSync(process.env.AUTH_QA_TLS_KEY),
  cert: fs.readFileSync(process.env.AUTH_QA_TLS_CERT),
}, (incoming, outgoing) => {
  const isApi = incoming.url.startsWith('/api/');
  const upstream = http.request({
    hostname: '127.0.0.1',
    port: isApi ? 5101 : 4300,
    path: incoming.url,
    method: incoming.method,
    headers: { ...incoming.headers, host: `127.0.0.1:${isApi ? 5101 : 4300}` },
  }, response => {
    outgoing.writeHead(response.statusCode || 502, response.headers);
    response.pipe(outgoing);
  });

  upstream.on('error', error => {
    if (!outgoing.headersSent) outgoing.writeHead(502);
    outgoing.end('Isolated QA upstream unavailable');
    console.error('QA_PROXY_UPSTREAM_ERROR', error.code);
  });
  incoming.pipe(upstream);
});

server.listen(4443, '127.0.0.1', () => {
  console.log('AUTH_QA_TLS_PROXY_READY');
});
