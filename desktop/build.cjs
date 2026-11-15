const fs = require("node:fs");
const path = require("node:path");
const { minify } = require("terser");

async function main() {
  const root = __dirname;
  const source = path.join(root, "src", "main.js");
  const outputDir = path.join(root, "build");
  const output = path.join(outputDir, "main.min.js");
  const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
  const packageJson = JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8"));

  if (!fs.existsSync(source)) throw new Error("Desktop source entry point is missing.");
  if (!html.includes('src="build/main.min.js"')) {
    throw new Error("index.html must load the minified release entry point.");
  }
  const releaseFiles = packageJson.build && packageJson.build.files;
  if (!Array.isArray(releaseFiles) || releaseFiles.includes("src/main.js") ||
      releaseFiles.includes("src/**") || releaseFiles.includes("**/*")) {
    throw new Error("Release file allow-list is missing or too broad; source files could be packaged.");
  }
  if (!releaseFiles.includes("build/main.min.js")) {
    throw new Error("Release file allow-list does not include the minified entry point.");
  }
  fs.mkdirSync(outputDir, { recursive: true });

  const result = await minify(fs.readFileSync(source, "utf8"), {
    compress: { passes: 2 },
    mangle: true,
    format: { comments: false }
  });
  if (!result.code || !result.code.trim()) throw new Error("Frontend minification produced no output.");

  const temporary = output + ".tmp";
  fs.writeFileSync(temporary, result.code, "utf8");
  try {
    fs.renameSync(temporary, output);
  } catch (error) {
    // Windows may refuse to replace an existing destination.
    if (!fs.existsSync(output)) throw error;
    fs.rmSync(output, { force: true });
    fs.renameSync(temporary, output);
  }
  const stat = fs.statSync(output);
  if (!stat.isFile() || stat.size === 0) throw new Error("Minified release entry point is empty.");
  console.log(`Prepared minified release frontend (${stat.size} bytes).`);
}

main().catch(error => {
  console.error("Release preparation failed:", error);
  process.exitCode = 1;
});
