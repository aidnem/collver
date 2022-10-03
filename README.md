# collver

Collver is an open source programming language focused on
ease-of-implementation.

Collver is a compiled language, and it is stack-based.

In theory, a hello world program in collver looks something like this:
```c
include "std.collver" // Include the standard library, which defines the `puts` procedure

proc main // The main procedure, like int main() in c
  "Hello, world!\n" // Initialize a null-terminated string, and push its pointer to the stack
  puts // Take this pointer, and use it to print the string to stdout
end
```

Unlike other programming languages that focus on silly things like memory
safety or ease-of-use, Collver is meant to be as simple to implement as
possible.

The reasons for this are as follows:

1. I'm clueless and have basically no idea how to write a compiler.
2. If I make the implementation simpler, it will be easier to rewrite in itself.

Collver will (hopefully) eventually be written in itself, but for now the
compiler is implemented in python.
