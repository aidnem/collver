from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional
import subprocess
import os
import sys

def run_echoed(cmd):
    print(f"[CMD] {' '.join(cmd)}")
    subprocess.run(cmd)

class TT(Enum):
    INT  = auto()
    WORD = auto()

@dataclass
class Token:
    typ   : TT
    value : str | int
    file  : str
    row   : int
    col   : int

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
    typ     : OT
    operand : Optional[int | Intrinsic]

def compiler_error(tok: Token, msg: str) -> None:
    """Print an error at a location, DOES NOT EXIT AUTOMATICALLY"""
    print(f"{tok.file}:{tok.row+1}:{tok.col+1}:ERROR: {msg}")

def lex_line(line: str) -> list[tuple[int, str]]:
    """Lexes a line, returning a list of pairs (col, str)"""
    # I realize that I could probably use split here, but I want to make it
    # easier for me to just 1:1 translate this code int Collver when I self-
    # host the language later (assuming I get that far before deleting the)
    # project ;).
    buffer = ""
    start_idx = 0
    chunks: list[tuple[int, str]] = []
    for idx, c in enumerate(line):
        if c == " " or c == "\n":
            if len(buffer) != 0:
                chunks.append((start_idx, buffer))
                buffer = ""
        else:
            if len(buffer) == 0:
                start_idx = idx
                buffer = c
            else:
                buffer += c

    if len(buffer) != 0:
        chunks.append((start_idx, buffer))
        buffer = ""
    return chunks

def lex_file(file_path) -> list[Token]:
    """Lex a file, returning Tokens including the tokens location, type, and value"""
    assert len(TT) == 2, "Exhaustive handling of Token Types in lex_file()"
    toks: list[Token] = []
    with open(file_path, "r") as f:
        for (row, line) in enumerate(f.readlines()):
            for (col, string) in lex_line(line):
                try:
                    val = int(string)
                    typ = TT.INT
                except ValueError:
                    val = string
                    typ = TT.WORD
                tok = Token(typ=typ, value=val, file=os.path.basename(file_path), row=row, col=col)
                toks.append(tok)
    return toks

STR_TO_INTRINSIC: dict[str, Intrinsic] = {
    "+": Intrinsic.PLUS,
    "print": Intrinsic.PRINT,
}

def parse_tokens_into_words(tokens: list[Token]) -> list[Word]:
    """Given a list of tokens, convert them into compile-able words"""
    assert len(OT) == 2, "Exhaustive handling of Op Types in parse_tokens_into_words()"
    rtokens = list(reversed(tokens))
    words = []
    while len(rtokens):
        tok = rtokens.pop()
        if tok.typ == TT.INT:
            assert type(tok.value) == int, "INT token had non-int value"
            words.append(Word(OT.PUSH_INT, int(tok.value)))
        elif tok.typ == TT.WORD:
            if tok.value in STR_TO_INTRINSIC:
                words.append(Word(OT.INTRINSIC, STR_TO_INTRINSIC[tok.value]))
            else:
                compiler_error(tok, f"Unknown word `{tok.value}`")
                sys.exit(1)

    return words

def compile_program(program: list[Word], out_file_path: str, bin_path: str):
    """Compile a series of Words into an executable file using `clang`"""
    assert len(OT) == 2, "Exhaustive handling of Op Types in compile_program()"
    assert len(Intrinsic) == 2, "Exhaustive handling of Intrincics in compile_program()"
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

    print(f"[INFO] Compiling `{out_file_path}` to native binary")
    run_echoed(["clang", out_file_path, "-o", bin_path])
    print(f"[INFO] Compiled source file to native binary at `{bin_path}`")

def repr_program(program: list[Word]):
    """Generate a pretty-printed string from a program"""
    return "[\n\t" + ",\n\t".join([str(i) for i in program]) + "\n]"

def usage():
    """Print a message on proper usage of the collver command"""
    print("""
USAGE: [python3.10] collver.py <filename> [flags]
    Flags:
        -r: Automatically run executable after compiling
    """[1:-5]) # Chop off the initial \n, the final \n, and the 4 spaces at the end

def main():
    if len(sys.argv) < 2:
        usage()
        print("ERROR: Not enough arguments provided")
        sys.exit(1)
    else:
        src_path = sys.argv[1]
        exec_path = os.path.splitext(src_path)[0]
        ll_path = exec_path + ".ll"
    toks = lex_file(src_path)
    program = parse_tokens_into_words(toks)
    compile_program(program, ll_path, exec_path)
    if not "/" in exec_path:
        exec_path = os.path.join(".", exec_path)
    if "-r" in sys.argv:
        print(f"[INFO] Running `{exec_path}`")
        subprocess.run([exec_path])

if __name__ == '__main__':
    main()
