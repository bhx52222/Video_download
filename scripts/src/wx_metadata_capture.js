// Activated with user approval: only channels.weixin.qq.com JSON responses.
// Never forwards cookies, request headers, or the original response body.
(function () {
  try {
    const body = $response.body || '';
    if (!body.includes('decodeKey')) { $done({}); return; }
    const data = JSON.parse(body.replace(/("decodeKey"\s*:\s*)(\d+)/g, '$1"$2"'));
    const rows = [];
    function visit(value, depth) {
      if (!value || typeof value !== 'object' || depth > 20 || rows.length >= 20) return;
      if (value.decodeKey && typeof value.url === 'string' && value.url.startsWith('https://finder.video.qq.com/')) {
        const key = String(value.decodeKey);
        if (/^\d{1,20}$/.test(key)) rows.push({url:value.url+(value.urlToken||''), decode_key:key, source:'channels.weixin.qq.com', at:Date.now()});
      }
      for (const k of Object.keys(value)) visit(value[k], depth+1);
    }
    visit(data,0);
    if (!rows.length) { $done({}); return; }
    $httpClient.post({url:'http://127.0.0.1:18787/metadata',headers:{'Content-Type':'application/json'},body:JSON.stringify(rows),timeout:2},()=> $done({}));
  } catch (_) { $done({}); }
})();
