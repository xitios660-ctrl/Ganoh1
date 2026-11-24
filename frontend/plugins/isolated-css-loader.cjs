const { stripRemoteFonts } = require('./isolated-resources.cjs');
module.exports = function isolatedCssLoader(source) { return stripRemoteFonts(source); };
