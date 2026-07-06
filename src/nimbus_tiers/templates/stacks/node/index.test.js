const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const { greet } = require("./index.js");

describe("greet", () => {
  it("returns Hello, World!", () => {
    assert.equal(greet(), "Hello, World!");
  });
});
