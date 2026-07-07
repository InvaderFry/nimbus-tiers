package main

import "fmt"

// Greet returns the canonical hello-world string. Exported so the starter
// test exercises a real function boundary rather than main().
func Greet() string {
	return "Hello, World!"
}

func main() {
	fmt.Println(Greet())
}
