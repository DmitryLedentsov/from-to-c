# From-To-C language notes

This document describes the prototype as it exists now, not a promise of a large future feature set.

## Goal

From-To-C explores a simple model:

> use high-level syntax for program structure, but lower it to ordinary portable C constructs.

C is the backend. The C compiler handles machine-code generation, optimization, linking, and target support.

The generated C does not need to be pretty enough to maintain by hand. It should be predictable, portable, and easy to inspect when debugging the transpiler.

## Current object model

A class is a value type in v0.1.

```text
class Point {
    float x;
    float y;
}
```

lowers to:

```c
typedef struct Point {
    double x;
    double y;
} Point;
```

There is no hidden object header and no runtime type information.

### Methods

```text
void move(float dx, float dy) {
    this.x = this.x + dx;
    this.y = this.y + dy;
}
```

lowers to a normal C function:

```c
static void Point_move(Point* self, double dx, double dy)
{
    self->x = (self->x + dx);
    self->y = (self->y + dy);
}
```

A call:

```text
point.move(1.0, 2.0);
```

becomes:

```c
Point_move(&point, 1.0, 2.0);
```

### Constructors

```text
Point(float x, float y) {
    this.x = x;
    this.y = y;
}
```

becomes a function returning the initialized value:

```c
static Point Point_init(double x, double y)
{
    Point self_value = {0};
    Point* self = &self_value;
    self->x = x;
    self->y = y;
    return self_value;
}
```

and:

```text
Point point = Point(1.5, 2.5);
```

becomes:

```c
Point point = Point_init(1.5, 2.5);
```

## Memory management

The first prototype deliberately avoids inventing a complicated ownership system before one is needed.

Current rule:

- class values are stored directly as C structs;
- local values live for their normal C scope;
- there is no `new`;
- there is no automatic heap allocation;
- there is no garbage collector;
- there is no reference counting;
- there is no mandatory runtime initialization.

For example:

```text
Point point = Point(1.0, 2.0);
```

is simply stack/value storage:

```c
Point point = Point_init(1.0, 2.0);
```

This keeps the first implementation honest: object syntax itself costs nothing beyond the C representation that it lowers to.

Heap/reference semantics should be designed only when real examples require them. They are intentionally not specified yet.

## Expressions and control flow

The current parser supports:

```text
+ - * /
== != < <= > >=
&& || !
```

and:

```text
if (condition) {
    ...
} else {
    ...
}

while (condition) {
    ...
}
```

These lower directly to the corresponding C operators and statements.

## Builtins

The prototype has two tiny output helpers:

```text
print_int(value);
print_float(value);
```

They currently lower through `printf`.

## Intentionally missing from v0.1

The following are not half-implemented; they are simply outside the first prototype:

- heap objects / `new`;
- inheritance;
- virtual methods and interfaces;
- generics;
- strings and containers;
- exceptions;
- modules/imports;
- direct C header import;
- exporting a stable C API;
- class-typed function parameters;
- method calls on temporary class values.

The next feature should be chosen from a concrete use case rather than added because a modern language is expected to have it.

## Project direction

The interesting long-term property is not merely "another language that emits C". A useful direction would be a high-level language that remains naturally compatible with C ecosystems and target toolchains:

```text
high-level source
      ↓
small, explicit lowering rules
      ↓
portable C
      ↓
existing C toolchain
```

Possible future experiments include direct C import/export and a small object/interface model, but the prototype should stay runtime-light and predictable.
