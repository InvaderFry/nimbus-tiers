function greet() {
  return "Hello, World!";
}

function main() {
  console.log(greet());
}

if (require.main === module) {
  main();
}

module.exports = { greet };
