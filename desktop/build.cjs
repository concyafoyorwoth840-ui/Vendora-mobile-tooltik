const fs = require("node:fs");
const path = require("node:path");
const { minify } = require("terser");

async function main() {
  const root = __dirname;
  const source = path.join(root, "src", "main.js");
  const outputDir = path.join(root, "build");
  const output = path.join(outputDir, "main.min.js");

  if (!fs.existsSync(source)) throw new Error("Desktop source entry point is missing.");
  fs.mkdirSync(outputDir, { recursive: true });

  const result = await minify(fs.readFileSync(source, "utf8"), {
    compress: { passes: 2 },
    mangle: true,
    format: { comments: false }
  });
  if (!result.code) throw new Error("Frontend minification produced no output.");

  const temporary = output + ".tmp";
  fs.writeFileSync(temporary, result.code, "utf8");
  fs.renameSync(temporary, output);
  console.log("Prepared minified release frontend.");
}

main().catch(error => {
  console.error("Release preparation failed:", error);
  process.exitCode = 1;
});
