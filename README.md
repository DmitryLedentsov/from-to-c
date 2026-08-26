# From-To-C

Experimental high-level language that transpiles to portable C and then uses a normal C compiler.

The project is intentionally small. The first prototype answers one question: can familiar class/method syntax lower to simple C without a VM, garbage collector, or compiler backend of our own?

```text
.ftc source
    ↓
ftc transpiler
    ↓
portable C11
    ↓
gcc / clang / another C compiler
    ↓
native binary
```

## Example

From-To-C:

```text
class Counter {
    int value;

    Counter(int initial) {
        this.value = initial;
    }

    void increment() {
        this.value = this.value + 1;
    }

    int get() {
        return this.value;
    }
}

int main() {
    Counter counter = Counter(0);

    while (counter.get() < 3) {
        counter.increment();
        print_int(counter.get());
    }

    return 0;
}
```

Generated C is ordinary structs and functions:

```c
typedef struct Counter {
    int value;
} Counter;

static void Counter_increment(Counter* self)
{
    self->value = (self->value + 1);
}

static int Counter_get(Counter* self)
{
    return self->value;
}
```

See [`examples/counter.ftc`](examples/counter.ftc) and its checked-in generated counterpart [`examples/generated/counter.c`](examples/generated/counter.c).

## Run

Requirements: Python 3 and a C11 compiler available as `cc`.

```bash
python3 src/ftc.py examples/counter.ftc -o counter.c
cc -std=c11 counter.c -o counter
./counter
```

Or transpile, compile, and run in one command:

```bash
python3 src/ftc.py examples/counter.ftc --run
```

Run all example checks:

```bash
make test
```

## Implemented in v0.1

- `class` declarations;
- fields;
- one constructor per class;
- instance methods;
- `int`, `float`, `bool`, `void`;
- local variables and assignment;
- arithmetic and comparisons;
- `if` / `else` and `while`;
- plain functions;
- `print_int` and `print_float` builtins;
- C11 output.

Classes are currently **value types**. A local class value becomes a C struct; a method becomes a C function that receives a pointer to that struct. There is no heap allocation, GC, reference counting, or language runtime in v0.1.

The language/design notes live in [`LANGUAGE.md`](LANGUAGE.md).
