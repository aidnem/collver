from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional
import subprocess
import os

def run_echoed(cmd):
    print(f"[CMD] {' '.join(cmd)}")
    subprocess.run(cmd)

class OT(Enum):
    """Operation Types of words"""
    PUSH_INT  = auto()
    INTRINSIC = auto()

class Intrinsic(Enum):
    """Intrinsic words"""
    PLUS  = auto()
    PRINT = auto()

@dataclass
class Word:
    """A word (instruction) in Collver"""
    typ: OT # Type of word
    operand: Optional[int | Intrinsic] # Operand

def compile_program(program: list[Word], out_file_path: str):
    print(f"[INFO] Generating {out_file_path}")
    with open(out_file_path, "w+") as out:
        # Push and pop operations
        out.write("@stack = global [1024 x i64] undef\n")
        out.write("@sp    = global i64 0\n")
        out.write("define void @push(i64 %val) {\n")
        out.write("  %sp = load i64, i64* @sp\n")
        out.write("  %addr = getelementptr [1024 x i64], [1024 x i64]* @stack, i64 0, i64 %sp\n")
        out.write("  store i64 %val, i64* %addr\n")
        out.write("  %newsp = add i64 %sp, 1\n")
        out.write("  store i64 %newsp, i64* @sp\n")
        out.write("  ret void\n")
        out.write("}\n")
        out.write("define i64 @pop() {\n")
        out.write("  %sp = load i64, i64* @sp\n")
        out.write("  %topsp = sub i64 %sp, 1\n")
        out.write("  %addr = getelementptr [1024 x i64], [1024 x i64]* @stack, i64 0, i64 %topsp\n")
        out.write("  %val = load i64, i64* %addr\n")
        out.write("  store i64 %topsp, i64* @sp\n")
        out.write("  ret i64 %val\n")
        out.write("}\n")
        out.write("declare i64 @printf(i8*, ...)")
        out.write("@fmt = private unnamed_addr constant [4 x i8] c\"%i\\0A\\00\"")
        out.write("define i64 @main() {\n")
        out.write("%fmtptr = getelementptr [4 x i8], [4 x i8]* @fmt, i64 0, i64 0\n")
        c: int = 0 # counter for unique numbers
        for word in program:
            out.write(f"  ; {str(word)}\n")
            if word.typ == OT.PUSH_INT:
                assert type(word.operand) == int, "PUSH_INT word has non-int type"
                out.write(f"  call void(i64) @push(i64 {word.operand})\n")
            elif word.typ == OT.INTRINSIC:
                assert type(word.operand) == Intrinsic, "Intrinsic word has non-intrinsic type"
                if word.operand == Intrinsic.PLUS:
                    out.write(f"  %a{c} = call i64() @pop()\n")
                    out.write(f"  %b{c} = call i64() @pop()\n")
                    out.write(f"  %c{c} = add i64 %a{c}, %b{c}\n")
                    out.write(f"  call void(i64) @push(i64 %c{c})\n")
                    c += 1
                elif word.operand == Intrinsic.PRINT:
                    out.write(f"  %a{c} = call i64() @pop()\n")
                    out.write(f"  call i64(i8*, ...) @printf(i8* %fmtptr, i64 %a{c})\n")
                    c += 1
                else:
                    assert False, f"Unknown Intrinsic {word}"
            else:
                assert False, f"Unknown Op Type {word}"

        out.write("  ret i64 0\n")
        out.write("}\n")

    print(f"[INFO] Compiling {out_file_path} to native binary")
    run_echoed(["clang", out_file_path, "-o", os.path.splitext(out_file_path)[0]])

def repr_program(program: list[Word]):
    return "[\n\t" + ",\n\t".join([str(i) for i in program]) + "\n]"

def main():
    program: list[Word] = [
        Word(OT.PUSH_INT, 10),
        Word(OT.PUSH_INT, 5),
        Word(OT.INTRINSIC, Intrinsic.PLUS),
        Word(OT.INTRINSIC, Intrinsic.PRINT),
    ]

    compile_program(program, "program.ll")

if __name__ == '__main__':
    main()
