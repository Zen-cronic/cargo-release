import assert from "node:assert/strict";
import { resolve } from "node:path";

import sharp from "sharp";

const [mode, sourceArg, outputArg, widthArg = "3600", heightArg = "2400"] = process.argv.slice(2);

assert.ok(mode === "architecture" || mode === "gallery", "mode must be architecture or gallery");
assert.ok(sourceArg, "source path is required");
assert.ok(outputArg, "output path is required");

const width = Number.parseInt(widthArg, 10);
const height = Number.parseInt(heightArg, 10);
assert.ok(Number.isInteger(width) && width > 0, "width must be a positive integer");
assert.ok(Number.isInteger(height) && height > 0, "height must be a positive integer");
assert.equal(width * 2, height * 3, "submission assets must use an exact 3:2 ratio");

const source = resolve(sourceArg);
const output = resolve(outputArg);
const image = sharp(source, mode === "architecture" ? { density: 192 } : undefined);

if (mode === "architecture") {
  await image.resize(width, height, { fit: "fill" }).png({ compressionLevel: 9 }).toFile(output);
} else {
  await image
    .resize(width, height, {
      fit: "contain",
      background: { r: 245, g: 248, b: 252, alpha: 1 },
    })
    .png({ compressionLevel: 9 })
    .toFile(output);
}

const metadata = await sharp(output).metadata();
assert.equal(metadata.width, width);
assert.equal(metadata.height, height);
console.log(`${mode}: ${source} -> ${output} (${metadata.width}x${metadata.height})`);
