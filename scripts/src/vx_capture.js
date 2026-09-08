// Surge MITM 脚本：把命中的媒体请求地址推给本地的 vx 接收端。
//
// 为什么用 Surge 而不是再装一个抓流工具：那类工具（res-downloader、
// wx_channels_download）的原理都是"本地代理 + MITM 根证书 + 改系统代理"，
// 和 Surge 是同一条技术路线，装了必然抢系统代理。Surge 已经在做这件事，
// 而且增强模式在网络层接管，连不遵守系统代理的微信客户端也能覆盖。
//
// 脚本类型：http-request。不读 body，开销极小。
const req = $request;
const h = req.headers || {};
if (Object.keys(h).some(k => k.toLowerCase() === "x-vx-probe")) {
  $done({});
} else {
const payload = {
  url: req.url,
  referer: h.Referer || h.referer || "",
  ua: h["User-Agent"] || h["user-agent"] || "",
  range: h.Range || h.range || "",
  ts: Date.now(),
};

$httpClient.post(
  {
    url: "http://127.0.0.1:18787/capture",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    timeout: 3,
  },
  function () {
    // 无论接收端在不在，都必须放行原请求，
    // 否则视频会卡住不播——那样连抓都抓不到。
    $done({});
  }
);

}
