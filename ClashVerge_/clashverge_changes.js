/**
 * ClashVerge 非港轮询脚本
 * 功能：创建非香港节点的负载均衡组，用于注册机等场景
 * 作者：Auto Generated
 * 日期：2026-03-19
 * 
 * 特性：
 * - 自动创建「🔁 非港轮询」负载均衡组
 * - 智能排除香港节点和流量信息节点
 * - 自动注入到合适的选择组
 * - 兼容所有订阅配置
 */

function uniqPrepend(arr, items) {
  if (!Array.isArray(arr)) arr = [];
  for (var i = items.length - 1; i >= 0; i--) {
    var item = items[i];
    var exists = false;
    for (var j = 0; j < arr.length; j++) {
      if (arr[j] === item) {
        exists = true;
        break;
      }
    }
    if (!exists) arr.unshift(item);
  }
  return arr;
}

function upsertGroup(groups, group) {
  for (var i = 0; i < groups.length; i++) {
    if (groups[i] && groups[i].name === group.name) {
      groups[i] = group;
      return groups;
    }
  }
  groups.unshift(group);
  return groups;
}

function main(config, profileName) {
  if (!config) return config;

  if (!Array.isArray(config["proxy-groups"])) {
    config["proxy-groups"] = [];
  }

  var groups = config["proxy-groups"];
  var LB_NAME = "🔁 非港轮询";

  var excludeRegex =
    "(?i)(" +
    "香港|hong[ -]?kong|\\bhk\\b|\\bhkg\\b|🇭🇰" +
    "|剩余流量|套餐到期|下次重置剩余|重置剩余|到期时间|流量重置" +
    "|traffic|expire|expiration|subscription|subscribe|reset|plan" +
    ")";

  groups = upsertGroup(groups, {
    name: LB_NAME,
    type: "load-balance",
    strategy: "round-robin",
    "include-all-proxies": true,
    "exclude-filter": excludeRegex,
    url: "https://www.gstatic.com/generate_204",
    interval: 300,
    lazy: true,
    "expected-status": 204
  });

  var injected = false;
  var entryNameRegex = /节点选择|代理|Proxy|PROXY|默认|GLOBAL|全局|选择/i;

  for (var i = 0; i < groups.length; i++) {
    var g = groups[i];
    if (!g || g.type !== "select") continue;

    if (entryNameRegex.test(g.name || "")) {
      if (!Array.isArray(g.proxies)) g.proxies = [];
      g.proxies = uniqPrepend(g.proxies, [LB_NAME]);
      injected = true;
    }
  }

  if (!injected) {
    for (var k = 0; k < groups.length; k++) {
      var g2 = groups[k];
      if (g2 && g2.type === "select") {
        if (!Array.isArray(g2.proxies)) g2.proxies = [];
        g2.proxies = uniqPrepend(g2.proxies, [LB_NAME]);
        break;
      }
    }
  }

  config["proxy-groups"] = groups;
  return config;
}