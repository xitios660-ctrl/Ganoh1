// Isolated desktop/owner bundles must not contact third-party telemetry or fonts.
// The normal web build continues to use its existing template and styles.
const HtmlWebpackPlugin = require('html-webpack-plugin');
function isolatedHtml(html) {
  return html
    .replace(/<link\b[^>]*href=["']https:\/\/fonts\.(?:googleapis|gstatic)\.com[^>]*>/gi, '')
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, script => script.includes('posthog.init(') ? '' : script);
}
class IsolatedResourcesPlugin {
  apply(compiler) {
    compiler.hooks.compilation.tap('GANOH isolated resources', compilation => {
      HtmlWebpackPlugin.getHooks(compilation).beforeEmit.tap('GANOH isolated resources', data => {
        data.html = isolatedHtml(data.html);
        return data;
      });
    });
  }
}
function stripRemoteFonts(source) {
  return source.replace(/@import\s+url\(["']?https:\/\/fonts\.googleapis\.com[^)]*\)\s*;/g, '');
}
module.exports = { IsolatedResourcesPlugin, isolatedHtml, stripRemoteFonts };
