const target = process.env.APP_URL ?? "http://127.0.0.1:3024";
const response = await fetch(target, { redirect: "manual" });
if (response.status !== 200) {
  throw new Error(`Expected 200 from ${target}, received ${response.status}`);
}
const body = await response.text();
if (!body.includes("Cargo Release")) {
  throw new Error("Cargo Release shell was not rendered");
}
console.log(`route smoke passed: ${target}`);
