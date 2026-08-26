#!/usr/bin/env python3
"""Tiny From-To-C prototype compiler.

Supported on purpose: classes as value types, fields, one constructor, methods,
plain functions, local variables, assignments, if/else, while, arithmetic,
comparisons, and print_int/print_float builtins.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


class CompileError(Exception):
    pass


@dataclass(frozen=True)
class Token:
    kind: str
    text: str
    pos: int


TOKEN_RE = re.compile(
    r"(?P<WS>\s+)"
    r"|(?P<COMMENT>//[^\n]*)"
    r"|(?P<NUMBER>\d+(?:\.\d+)?)"
    r"|(?P<IDENT>[A-Za-z_][A-Za-z0-9_]*)"
    r"|(?P<OP>==|!=|<=|>=|&&|\|\||[{}()\[\];,.=+\-*/<>!])"
)


def tokenize(source: str) -> list[Token]:
    tokens: list[Token] = []
    pos = 0
    while pos < len(source):
        match = TOKEN_RE.match(source, pos)
        if not match:
            raise CompileError(f"unexpected character {source[pos]!r} at offset {pos}")
        kind = match.lastgroup
        text = match.group()
        if kind not in {"WS", "COMMENT"}:
            tokens.append(Token(kind or "", text, pos))
        pos = match.end()
    tokens.append(Token("EOF", "<eof>", len(source)))
    return tokens


@dataclass
class Program:
    classes: list[ClassDecl]
    functions: list[FunctionDecl]


@dataclass
class Param:
    type_name: str
    name: str


@dataclass
class FieldDecl:
    type_name: str
    name: str


@dataclass
class ConstructorDecl:
    params: list[Param]
    body: Block


@dataclass
class MethodDecl:
    return_type: str
    name: str
    params: list[Param]
    body: Block


@dataclass
class ClassDecl:
    name: str
    fields: list[FieldDecl]
    constructor: ConstructorDecl | None
    methods: list[MethodDecl]


@dataclass
class FunctionDecl:
    return_type: str
    name: str
    params: list[Param]
    body: Block


class Stmt:
    pass


@dataclass
class Block(Stmt):
    statements: list[Stmt]


@dataclass
class VarDecl(Stmt):
    type_name: str
    name: str
    initializer: Expr | None


@dataclass
class Assign(Stmt):
    target: Expr
    value: Expr


@dataclass
class ExprStmt(Stmt):
    expr: Expr


@dataclass
class ReturnStmt(Stmt):
    value: Expr | None


@dataclass
class IfStmt(Stmt):
    condition: Expr
    then_block: Block
    else_block: Block | None


@dataclass
class WhileStmt(Stmt):
    condition: Expr
    body: Block


class Expr:
    pass


@dataclass
class Number(Expr):
    text: str


@dataclass
class BoolLiteral(Expr):
    value: bool


@dataclass
class Var(Expr):
    name: str


@dataclass
class FieldAccess(Expr):
    receiver: Expr
    name: str


@dataclass
class Call(Expr):
    name: str
    args: list[Expr]


@dataclass
class MethodCall(Expr):
    receiver: Expr
    name: str
    args: list[Expr]


@dataclass
class Unary(Expr):
    op: str
    operand: Expr


@dataclass
class Binary(Expr):
    left: Expr
    op: str
    right: Expr


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.i = 0

    def peek(self, offset: int = 0) -> Token:
        return self.tokens[min(self.i + offset, len(self.tokens) - 1)]

    def at(self, text: str) -> bool:
        return self.peek().text == text

    def take(self) -> Token:
        token = self.peek()
        self.i += 1
        return token

    def expect(self, text: str) -> Token:
        token = self.peek()
        if token.text != text:
            raise CompileError(f"expected {text!r}, got {token.text!r} at offset {token.pos}")
        self.i += 1
        return token

    def expect_ident(self) -> str:
        token = self.peek()
        if token.kind != "IDENT":
            raise CompileError(f"expected identifier, got {token.text!r} at offset {token.pos}")
        self.i += 1
        return token.text

    def parse_program(self) -> Program:
        classes: list[ClassDecl] = []
        functions: list[FunctionDecl] = []
        while self.peek().kind != "EOF":
            if self.at("class"):
                classes.append(self.parse_class())
            else:
                functions.append(self.parse_function())
        return Program(classes, functions)

    def parse_type(self) -> str:
        return self.expect_ident()

    def parse_params(self) -> list[Param]:
        self.expect("(")
        params: list[Param] = []
        if not self.at(")"):
            while True:
                params.append(Param(self.parse_type(), self.expect_ident()))
                if not self.at(","):
                    break
                self.take()
        self.expect(")")
        return params

    def parse_class(self) -> ClassDecl:
        self.expect("class")
        name = self.expect_ident()
        self.expect("{")
        fields: list[FieldDecl] = []
        methods: list[MethodDecl] = []
        constructor: ConstructorDecl | None = None

        while not self.at("}"):
            first = self.expect_ident()
            if first == name and self.at("("):
                if constructor is not None:
                    raise CompileError(f"class {name} has more than one constructor")
                constructor = ConstructorDecl(self.parse_params(), self.parse_block())
                continue

            second = self.expect_ident()
            if self.at(";"):
                self.take()
                fields.append(FieldDecl(first, second))
            elif self.at("("):
                methods.append(MethodDecl(first, second, self.parse_params(), self.parse_block()))
            else:
                token = self.peek()
                raise CompileError(f"expected ';' or '(' at offset {token.pos}")

        self.expect("}")
        return ClassDecl(name, fields, constructor, methods)

    def parse_function(self) -> FunctionDecl:
        return_type = self.parse_type()
        name = self.expect_ident()
        params = self.parse_params()
        body = self.parse_block()
        return FunctionDecl(return_type, name, params, body)

    def parse_block(self) -> Block:
        self.expect("{")
        statements: list[Stmt] = []
        while not self.at("}"):
            statements.append(self.parse_statement())
        self.expect("}")
        return Block(statements)

    def parse_statement(self) -> Stmt:
        if self.at("return"):
            self.take()
            if self.at(";"):
                self.take()
                return ReturnStmt(None)
            value = self.parse_expression()
            self.expect(";")
            return ReturnStmt(value)

        if self.at("if"):
            self.take()
            self.expect("(")
            condition = self.parse_expression()
            self.expect(")")
            then_block = self.parse_block()
            else_block = None
            if self.at("else"):
                self.take()
                else_block = self.parse_block()
            return IfStmt(condition, then_block, else_block)

        if self.at("while"):
            self.take()
            self.expect("(")
            condition = self.parse_expression()
            self.expect(")")
            return WhileStmt(condition, self.parse_block())

        if self.peek().kind == "IDENT" and self.peek(1).kind == "IDENT":
            type_name = self.take().text
            name = self.take().text
            initializer = None
            if self.at("="):
                self.take()
                initializer = self.parse_expression()
            self.expect(";")
            return VarDecl(type_name, name, initializer)

        expr = self.parse_expression()
        if self.at("="):
            self.take()
            value = self.parse_expression()
            self.expect(";")
            return Assign(expr, value)
        self.expect(";")
        return ExprStmt(expr)

    def parse_expression(self) -> Expr:
        return self.parse_or()

    def parse_or(self) -> Expr:
        expr = self.parse_and()
        while self.at("||"):
            expr = Binary(expr, self.take().text, self.parse_and())
        return expr

    def parse_and(self) -> Expr:
        expr = self.parse_equality()
        while self.at("&&"):
            expr = Binary(expr, self.take().text, self.parse_equality())
        return expr

    def parse_equality(self) -> Expr:
        expr = self.parse_comparison()
        while self.at("==") or self.at("!="):
            expr = Binary(expr, self.take().text, self.parse_comparison())
        return expr

    def parse_comparison(self) -> Expr:
        expr = self.parse_additive()
        while self.at("<") or self.at("<=") or self.at(">") or self.at(">="):
            expr = Binary(expr, self.take().text, self.parse_additive())
        return expr

    def parse_additive(self) -> Expr:
        expr = self.parse_multiplicative()
        while self.at("+") or self.at("-"):
            expr = Binary(expr, self.take().text, self.parse_multiplicative())
        return expr

    def parse_multiplicative(self) -> Expr:
        expr = self.parse_unary()
        while self.at("*") or self.at("/"):
            expr = Binary(expr, self.take().text, self.parse_unary())
        return expr

    def parse_unary(self) -> Expr:
        if self.at("-") or self.at("!"):
            return Unary(self.take().text, self.parse_unary())
        return self.parse_postfix()

    def parse_postfix(self) -> Expr:
        expr = self.parse_primary()
        while True:
            if self.at("("):
                if not isinstance(expr, Var):
                    raise CompileError("only named functions/constructors can be called directly")
                expr = Call(expr.name, self.parse_args())
            elif self.at("."):
                self.take()
                name = self.expect_ident()
                if self.at("("):
                    expr = MethodCall(expr, name, self.parse_args())
                else:
                    expr = FieldAccess(expr, name)
            else:
                break
        return expr

    def parse_args(self) -> list[Expr]:
        self.expect("(")
        args: list[Expr] = []
        if not self.at(")"):
            while True:
                args.append(self.parse_expression())
                if not self.at(","):
                    break
                self.take()
        self.expect(")")
        return args

    def parse_primary(self) -> Expr:
        token = self.peek()
        if token.kind == "NUMBER":
            self.take()
            return Number(token.text)
        if token.text == "true":
            self.take()
            return BoolLiteral(True)
        if token.text == "false":
            self.take()
            return BoolLiteral(False)
        if token.kind == "IDENT":
            self.take()
            return Var(token.text)
        if token.text == "(":
            self.take()
            expr = self.parse_expression()
            self.expect(")")
            return expr
        raise CompileError(f"expected expression, got {token.text!r} at offset {token.pos}")


BUILTIN_TYPES = {"void", "int", "float", "bool"}
C_TYPES = {"void": "void", "int": "int", "float": "double", "bool": "bool"}


@dataclass
class VarInfo:
    type_name: str
    is_parameter: bool = False


class Generator:
    def __init__(self, program: Program):
        self.program = program
        self.classes = {c.name: c for c in program.classes}
        self.functions = {f.name: f for f in program.functions}
        self.lines: list[str] = []
        self.indent = 0
        self.current_class: ClassDecl | None = None
        self.env: dict[str, VarInfo] = {}
        self.validate()

    def validate(self) -> None:
        if len(self.classes) != len(self.program.classes):
            raise CompileError("duplicate class name")
        if len(self.functions) != len(self.program.functions):
            raise CompileError("duplicate function name")
        for cls in self.program.classes:
            field_names = [f.name for f in cls.fields]
            method_names = [m.name for m in cls.methods]
            if len(field_names) != len(set(field_names)):
                raise CompileError(f"duplicate field in class {cls.name}")
            if len(method_names) != len(set(method_names)):
                raise CompileError(f"duplicate method in class {cls.name}")
            for field in cls.fields:
                self.require_type(field.type_name)
            if cls.constructor:
                for param in cls.constructor.params:
                    self.require_type(param.type_name)
            for method in cls.methods:
                self.require_type(method.return_type)
                for param in method.params:
                    self.require_type(param.type_name)
        for func in self.program.functions:
            self.require_type(func.return_type)
            for param in func.params:
                self.require_type(param.type_name)

    def require_type(self, type_name: str) -> None:
        if type_name not in BUILTIN_TYPES and type_name not in self.classes:
            raise CompileError(f"unknown type {type_name}")

    def emit(self, line: str = "") -> None:
        self.lines.append("    " * self.indent + line)

    def c_type(self, type_name: str) -> str:
        return C_TYPES.get(type_name, type_name)

    def generate(self) -> str:
        self.emit("/* Generated by ftc. Do not edit by hand. */")
        self.emit("#include <stdbool.h>")
        self.emit("#include <stdio.h>")
        self.emit()
        self.emit("#define print_int(value) printf(\"%d\\n\", (value))")
        self.emit("#define print_float(value) printf(\"%g\\n\", (value))")
        self.emit()

        for cls in self.program.classes:
            self.emit(f"typedef struct {cls.name} {{")
            self.indent += 1
            for field in cls.fields:
                self.emit(f"{self.c_type(field.type_name)} {field.name};")
            self.indent -= 1
            self.emit(f"}} {cls.name};")
            self.emit()

        for cls in self.program.classes:
            if cls.constructor:
                self.emit(self.constructor_signature(cls) + ";")
            for method in cls.methods:
                self.emit(self.method_signature(cls, method) + ";")
        for func in self.program.functions:
            self.emit(self.function_signature(func) + ";")
        self.emit()

        for cls in self.program.classes:
            if cls.constructor:
                self.generate_constructor(cls, cls.constructor)
                self.emit()
            for method in cls.methods:
                self.generate_method(cls, method)
                self.emit()

        for func in self.program.functions:
            self.generate_function(func)
            self.emit()

        return "\n".join(self.lines).rstrip() + "\n"

    def params_c(self, params: list[Param]) -> str:
        if not params:
            return "void"
        return ", ".join(f"{self.c_type(p.type_name)} {p.name}" for p in params)

    def constructor_signature(self, cls: ClassDecl) -> str:
        assert cls.constructor
        return f"static {cls.name} {cls.name}_init({self.params_c(cls.constructor.params)})"

    def method_signature(self, cls: ClassDecl, method: MethodDecl) -> str:
        tail = ""
        if method.params:
            tail = ", " + ", ".join(
                f"{self.c_type(p.type_name)} {p.name}" for p in method.params
            )
        return f"static {self.c_type(method.return_type)} {cls.name}_{method.name}({cls.name}* self{tail})"

    def function_signature(self, func: FunctionDecl) -> str:
        prefix = "" if func.name == "main" else "static "
        return f"{prefix}{self.c_type(func.return_type)} {func.name}({self.params_c(func.params)})"

    def generate_constructor(self, cls: ClassDecl, ctor: ConstructorDecl) -> None:
        self.current_class = cls
        self.env = {p.name: VarInfo(p.type_name, True) for p in ctor.params}
        self.emit(self.constructor_signature(cls))
        self.emit("{")
        self.indent += 1
        self.emit(f"{cls.name} self_value = {{0}};")
        self.emit(f"{cls.name}* self = &self_value;")
        self.generate_statements(ctor.body)
        self.emit("return self_value;")
        self.indent -= 1
        self.emit("}")
        self.current_class = None
        self.env = {}

    def generate_method(self, cls: ClassDecl, method: MethodDecl) -> None:
        self.current_class = cls
        self.env = {p.name: VarInfo(p.type_name, True) for p in method.params}
        self.emit(self.method_signature(cls, method))
        self.emit("{")
        self.indent += 1
        self.generate_statements(method.body)
        self.indent -= 1
        self.emit("}")
        self.current_class = None
        self.env = {}

    def generate_function(self, func: FunctionDecl) -> None:
        self.current_class = None
        self.env = {p.name: VarInfo(p.type_name, True) for p in func.params}
        self.emit(self.function_signature(func))
        self.emit("{")
        self.indent += 1
        self.generate_statements(func.body)
        self.indent -= 1
        self.emit("}")
        self.env = {}

    def generate_statements(self, block: Block) -> None:
        for stmt in block.statements:
            self.generate_statement(stmt)

    def generate_statement(self, stmt: Stmt) -> None:
        if isinstance(stmt, VarDecl):
            self.require_type(stmt.type_name)
            if stmt.name in self.env:
                raise CompileError(f"variable {stmt.name} already declared")
            if stmt.initializer is None:
                self.emit(f"{self.c_type(stmt.type_name)} {stmt.name} = {{0}};")
            else:
                actual = self.expr_type(stmt.initializer)
                self.require_assignable(stmt.type_name, actual)
                self.emit(
                    f"{self.c_type(stmt.type_name)} {stmt.name} = {self.expr_c(stmt.initializer)};"
                )
            self.env[stmt.name] = VarInfo(stmt.type_name)
            return

        if isinstance(stmt, Assign):
            target_type = self.expr_type(stmt.target)
            value_type = self.expr_type(stmt.value)
            self.require_assignable(target_type, value_type)
            self.emit(f"{self.lvalue_c(stmt.target)} = {self.expr_c(stmt.value)};")
            return

        if isinstance(stmt, ExprStmt):
            self.emit(f"{self.expr_c(stmt.expr)};")
            return

        if isinstance(stmt, ReturnStmt):
            if stmt.value is None:
                self.emit("return;")
            else:
                self.emit(f"return {self.expr_c(stmt.value)};")
            return

        if isinstance(stmt, IfStmt):
            self.emit(f"if ({self.expr_c(stmt.condition)}) {{")
            self.indent += 1
            self.generate_statements(stmt.then_block)
            self.indent -= 1
            if stmt.else_block:
                self.emit("} else {")
                self.indent += 1
                self.generate_statements(stmt.else_block)
                self.indent -= 1
            self.emit("}")
            return

        if isinstance(stmt, WhileStmt):
            self.emit(f"while ({self.expr_c(stmt.condition)}) {{")
            self.indent += 1
            self.generate_statements(stmt.body)
            self.indent -= 1
            self.emit("}")
            return

        raise CompileError(f"unsupported statement {type(stmt).__name__}")

    def require_assignable(self, expected: str, actual: str) -> None:
        if expected == actual:
            return
        if expected == "float" and actual == "int":
            return
        raise CompileError(f"cannot assign {actual} to {expected}")

    def field(self, class_name: str, field_name: str) -> FieldDecl:
        cls = self.classes.get(class_name)
        if not cls:
            raise CompileError(f"{class_name} is not a class")
        for field in cls.fields:
            if field.name == field_name:
                return field
        raise CompileError(f"class {class_name} has no field {field_name}")

    def method(self, class_name: str, method_name: str) -> MethodDecl:
        cls = self.classes.get(class_name)
        if not cls:
            raise CompileError(f"{class_name} is not a class")
        for method in cls.methods:
            if method.name == method_name:
                return method
        raise CompileError(f"class {class_name} has no method {method_name}")

    def expr_type(self, expr: Expr) -> str:
        if isinstance(expr, Number):
            return "float" if "." in expr.text else "int"
        if isinstance(expr, BoolLiteral):
            return "bool"
        if isinstance(expr, Var):
            if expr.name == "this":
                if not self.current_class:
                    raise CompileError("'this' is only valid inside a class")
                return self.current_class.name
            info = self.env.get(expr.name)
            if not info:
                raise CompileError(f"unknown variable {expr.name}")
            return info.type_name
        if isinstance(expr, FieldAccess):
            return self.field(self.expr_type(expr.receiver), expr.name).type_name
        if isinstance(expr, Call):
            if expr.name in self.classes:
                cls = self.classes[expr.name]
                if not cls.constructor and expr.args:
                    raise CompileError(f"class {expr.name} has no constructor")
                return expr.name
            if expr.name == "print_int" or expr.name == "print_float":
                return "void"
            func = self.functions.get(expr.name)
            if not func:
                raise CompileError(f"unknown function {expr.name}")
            return func.return_type
        if isinstance(expr, MethodCall):
            class_name = self.expr_type(expr.receiver)
            return self.method(class_name, expr.name).return_type
        if isinstance(expr, Unary):
            return "bool" if expr.op == "!" else self.expr_type(expr.operand)
        if isinstance(expr, Binary):
            if expr.op in {"==", "!=", "<", "<=", ">", ">=", "&&", "||"}:
                return "bool"
            left = self.expr_type(expr.left)
            right = self.expr_type(expr.right)
            if left == "float" or right == "float":
                return "float"
            return "int"
        raise CompileError(f"cannot infer type for {type(expr).__name__}")

    def expr_c(self, expr: Expr) -> str:
        if isinstance(expr, Number):
            return expr.text
        if isinstance(expr, BoolLiteral):
            return "true" if expr.value else "false"
        if isinstance(expr, Var):
            return "self" if expr.name == "this" else expr.name
        if isinstance(expr, FieldAccess):
            if isinstance(expr.receiver, Var) and expr.receiver.name == "this":
                return f"self->{expr.name}"
            return f"{self.expr_c(expr.receiver)}.{expr.name}"
        if isinstance(expr, Call):
            args = ", ".join(self.expr_c(a) for a in expr.args)
            if expr.name in self.classes:
                cls = self.classes[expr.name]
                if cls.constructor:
                    return f"{expr.name}_init({args})"
                if expr.args:
                    raise CompileError(f"class {expr.name} has no constructor")
                return f"({expr.name}){{0}}"
            return f"{expr.name}({args})"
        if isinstance(expr, MethodCall):
            class_name = self.expr_type(expr.receiver)
            receiver = self.receiver_pointer_c(expr.receiver)
            args = [receiver] + [self.expr_c(a) for a in expr.args]
            return f"{class_name}_{expr.name}({', '.join(args)})"
        if isinstance(expr, Unary):
            return f"({expr.op}{self.expr_c(expr.operand)})"
        if isinstance(expr, Binary):
            return f"({self.expr_c(expr.left)} {expr.op} {self.expr_c(expr.right)})"
        raise CompileError(f"cannot generate expression {type(expr).__name__}")

    def receiver_pointer_c(self, expr: Expr) -> str:
        if isinstance(expr, Var):
            if expr.name == "this":
                return "self"
            info = self.env.get(expr.name)
            if info and info.is_parameter and info.type_name in self.classes:
                raise CompileError("class-typed function/method parameters are not supported yet")
            return f"&{expr.name}"
        raise CompileError("v0.1 method receiver must be a named local variable or 'this'")

    def lvalue_c(self, expr: Expr) -> str:
        if isinstance(expr, Var):
            if expr.name == "this":
                raise CompileError("cannot assign to 'this'")
            if expr.name not in self.env:
                raise CompileError(f"unknown variable {expr.name}")
            return expr.name
        if isinstance(expr, FieldAccess):
            if isinstance(expr.receiver, Var) and expr.receiver.name == "this":
                return f"self->{expr.name}"
            return f"{self.expr_c(expr.receiver)}.{expr.name}"
        raise CompileError("left side of assignment is not assignable")


def compile_source(source: str) -> str:
    program = Parser(tokenize(source)).parse_program()
    return Generator(program).generate()


def main() -> int:
    parser = argparse.ArgumentParser(prog="ftc", description="From-To-C prototype transpiler")
    parser.add_argument("source", type=Path, help="input .ftc file")
    parser.add_argument("-o", "--output", type=Path, help="generated C path")
    parser.add_argument("--run", action="store_true", help="compile generated C with cc and run it")
    args = parser.parse_args()

    output = args.output or args.source.with_suffix(".c")
    try:
        generated = compile_source(args.source.read_text(encoding="utf-8"))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(generated, encoding="utf-8")
    except (CompileError, OSError) as exc:
        print(f"ftc: error: {exc}", file=sys.stderr)
        return 1

    print(f"generated {output}")

    if args.run:
        binary = output.with_suffix("")
        completed = subprocess.run(
            ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", str(output), "-o", str(binary)]
        )
        if completed.returncode != 0:
            return completed.returncode
        return subprocess.run([str(binary.resolve())]).returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
