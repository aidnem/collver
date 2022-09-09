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
    typ   : TT        # Token type (word or different values)
    value : str | int # Value (word str or int value)
    file  : str       # File that the token originated in
    row   : int       # Row that the token is on (0 indexed)
    col   : int       # Row that the token is on (0 indexed)

class OT(Enum):
    """Operation Types of words"""
    PUSH_INT  = auto()
    KEYWORD   = auto()
    INTRINSIC = auto()

class Keyword(Enum):
    """Keywords (words that aren't Intrinsics)"""
    IF   = auto()
    DO   = auto()
    ELSE = auto()
    END  = auto()

class Intrinsic(Enum):
    """Intrinsic words"""
    PLUS  = auto()
    MINUS = auto()
    MULT  = auto()
    DIV   = auto()
    MOD   = auto()
    SHL   = auto()
    SHR   = auto()
    DUP   = auto()
    DROP  = auto()
    PRINT = auto()

@dataclass
class Word:
    """A word (instruction) in Collver"""
    typ     : OT                                  # Type of token (for different syntaxes)
    operand : Optional[int | Intrinsic | Keyword] # Value or type of keyword/intrinsic
    tok     : Token                               # Token that the word was derived from
    jmp     : Optional[int]                       # Jump location for control flow words

def compiler_error(tok: Token, msg: str) -> None:
    """Print an error at a location, DOES NOT EXIT AUTOMATICALLY"""
    print(f"{tok.file}:{tok.row+1}:{tok.col+1}:ERROR: {msg}", file=sys.stderr)

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


assert len(Keyword) == 4, "Exhaustive map of Words in STR_TO_KEYWORD"
STR_TO_KEYWORD: dict[str, Keyword] = {
    "if": Keyword.IF,
    "do": Keyword.DO,
    "else": Keyword.ELSE,
    "end": Keyword.END,
}

assert len(Intrinsic) == 10, "Exhaustive map of Intrinsics in STR_TO_INTRINSIC"
STR_TO_INTRINSIC: dict[str, Intrinsic] = {
    "+": Intrinsic.PLUS,
    "-": Intrinsic.MINUS,
    "*": Intrinsic.MULT,
    "/": Intrinsic.DIV,
    "%": Intrinsic.MOD,
    "<<": Intrinsic.SHL,
    ">>": Intrinsic.SHR,
    "dup": Intrinsic.DUP,
    "drop": Intrinsic.DROP,
    "print": Intrinsic.PRINT,
}

def parse_tokens_into_words(tokens: list[Token]) -> list[Word]:
    """Given a list of tokens, convert them into compile-able words"""
    assert len(OT) == 3, "Exhaustive handling of Op Types in parse_tokens_into_words()"
    rtokens = list(reversed(tokens))
    words = []
    while len(rtokens):
        tok = rtokens.pop()
        if tok.typ == TT.INT:
            assert type(tok.value) == int, "INT token had non-int value"
            words.append(Word(OT.PUSH_INT, int(tok.value), tok, None))
        elif tok.typ == TT.WORD:
            if tok.value in STR_TO_KEYWORD:
                words.append(Word(OT.KEYWORD, STR_TO_KEYWORD[tok.value], tok, None))
            elif tok.value in STR_TO_INTRINSIC:
                words.append(Word(OT.INTRINSIC, STR_TO_INTRINSIC[tok.value], tok, None))
            else:
                compiler_error(tok, f"Unknown word `{tok.value}`")
                sys.exit(1)
        else:
            assert False, f"Unkown token type {tok.typ}"

    return words

def crossreference_program(program: list[Word]) -> None:
    """Given a program, set the correct index to jump to for control flow words"""
    assert len(OT) == 3, "Exhaustive handling of Op Types in crossreference_program()"
    assert len(Intrinsic) == 10, "Exhaustive handling of Intrincics in crossreference_program()"
    assert len(Keyword) == 4, "Exhaustive handling of Keywords in crossreference_program()"
    stack: list[int] = []
    for ip, word in enumerate(program):
        if word.typ == OT.KEYWORD:
            if word.operand == Keyword.IF:
                stack.append(ip)
            elif word.operand == Keyword.DO:
                stack.append(ip)
            elif word.operand == Keyword.ELSE:
                try:
                    do_ip = stack.pop()
                    start_ip = stack.pop()
                except IndexError:
                    compiler_error(word.tok, "Word `else` with no start of block")
                    sys.exit(1)

                start_word = program[start_ip]
                if start_word.operand == Keyword.IF:
                    word.jmp = ip
                else:
                    compiler_error(word.tok, "Word `else` can only close `if` block")
                    sys.exit(1)

                program[do_ip].jmp = ip

                stack.append(start_ip)
                stack.append(ip)
            elif word.operand == Keyword.END:
                try:
                    do_ip = stack.pop()
                    start_ip = stack.pop()
                except IndexError:
                    compiler_error(word.tok, "Word `end` with no start of block")
                    sys.exit(1)

                start_word = program[start_ip]
                if start_word.operand == Keyword.IF:
                    word.jmp = ip
                else:
                    assert False, f"Unknown start of `end` block {start_word}"

                program[do_ip].jmp = ip

    if len(stack) != 0:
      compiler_error(program[stack.pop()].tok, f"Unclosed block")
      print(stack)
      sys.exit(1)

def compile_program_to_ll(program: list[Word], out_file_path: str):
    """Compile a series of Words into an llvm IR file (.ll)"""
    assert len(OT) == 3, "Exhaustive handling of Op Types in compile_program()"
    assert len(Intrinsic) == 10, "Exhaustive handling of Intrincics in compile_program()"
    assert len(Keyword) == 4, "Exhaustive handling of Keywords in compile_program()"
    print(f"[INFO] Generating {out_file_path}")
    with open(out_file_path, "w+") as out:
        # Push and pop operations
        out.write("@stack = global [1024 x i32] undef\n")
        out.write("@sp    = global i32 0\n")
        out.write("define void @push(i32 %val) {\n")
        out.write("  %sp = load i32, i32* @sp\n")
        out.write("  %addr = getelementptr [1024 x i32], [1024 x i32]* @stack, i32 0, i32 %sp\n")
        out.write("  store i32 %val, i32* %addr\n")
        out.write("  %newsp = add i32 %sp, 1\n")
        out.write("  store i32 %newsp, i32* @sp\n")
        out.write("  ret void\n")
        out.write("}\n")
        out.write("define i32 @pop() {\n")
        out.write("  %sp = load i32, i32* @sp\n")
        out.write("  %topsp = sub i32 %sp, 1\n")
        out.write("  %addr = getelementptr [1024 x i32], [1024 x i32]* @stack, i32 0, i32 %topsp\n")
        out.write("  %val = load i32, i32* %addr\n")
        out.write("  store i32 %topsp, i32* @sp\n")
        out.write("  ret i32 %val\n")
        out.write("}\n")
        out.write("declare i32 @printf(i8*, ...)")
        out.write("@fmt = private unnamed_addr constant [4 x i8] c\"%i\\0A\\00\"")
        out.write("define i32 @main() {\n")
        out.write("%fmtptr = getelementptr [4 x i8], [4 x i8]* @fmt, i32 0, i32 0\n")
        c: int = 0 # counter for unique numbers
        for ip, word in enumerate(program):
            out.write(f"  ; {str(word)}\n")
            if word.typ == OT.PUSH_INT:
                assert type(word.operand) == int, "PUSH_INT word has non-int type"
                out.write(f"  call void(i32) @push(i32 {word.operand})\n")
            elif word.typ == OT.KEYWORD:
                if word.operand == Keyword.IF:
                    pass
                elif word.operand == Keyword.DO:
                    out.write(f"  %a{c} = call i32() @pop()\n")
                    # Compare number with 0 (true if a{n} != 0)
                    out.write(f"  %b{c} = icmp ne i32 %a{c}, 0\n")
                    # Jump to right in front if true, or `end` if false
                    out.write(f"  br i1 %b{c}, label %l{ip}, label %l{word.jmp}\n")
                    out.write(f"l{ip}:\n") # Label to jump to if true
                    c += 1
                elif word.operand == Keyword.ELSE:
                    out.write(f"  br label %l{word.jmp}\n")
                    out.write(f"l{ip}:\n")
                elif word.operand == Keyword.END:
                    out.write(f"  br label %l{word.jmp}\n")
                    out.write(f"l{ip}:\n")
            elif word.typ == OT.INTRINSIC:
                assert type(word.operand) == Intrinsic, "Intrinsic word has non-intrinsic type"
                if word.operand == Intrinsic.PLUS:
                    out.write(f"  %a{c} = call i32() @pop()\n")
                    out.write(f"  %b{c} = call i32() @pop()\n")
                    out.write(f"  %c{c} = add i32 %a{c}, %b{c}\n")
                    out.write(f"  call void(i32) @push(i32 %c{c})\n")
                    c += 1
                elif word.operand == Intrinsic.MINUS:
                    out.write(f"  %a{c} = call i32() @pop()\n")
                    out.write(f"  %b{c} = call i32() @pop()\n")
                    out.write(f"  %c{c} = sub i32 %b{c}, %a{c}\n")
                    out.write(f"  call void(i32) @push(i32 %c{c})\n")
                    c += 1
                elif word.operand == Intrinsic.MULT:
                    out.write(f"  %a{c} = call i32() @pop()\n")
                    out.write(f"  %b{c} = call i32() @pop()\n")
                    out.write(f"  %c{c} = mul i32 %a{c}, %b{c}\n")
                    out.write(f"  call void(i32) @push(i32 %c{c})\n")
                    c += 1
                elif word.operand == Intrinsic.DIV:
                    out.write(f"  %a{c} = call i32() @pop()\n")
                    out.write(f"  %b{c} = call i32() @pop()\n")
                    out.write(f"  %c{c} = sdiv i32 %b{c}, %a{c}\n")
                    out.write(f"  call void(i32) @push(i32 %c{c})\n")
                    c += 1
                elif word.operand == Intrinsic.MOD:
                    out.write(f"  %a{c} = call i32() @pop()\n")
                    out.write(f"  %b{c} = call i32() @pop()\n")
                    out.write(f"  %c{c} = srem i32 %b{c}, %a{c}\n")
                    out.write(f"  call void(i32) @push(i32 %c{c})\n")
                    c += 1
                elif word.operand == Intrinsic.SHL:
                    out.write(f"  %a{c} = call i32() @pop()\n")
                    out.write(f"  %b{c} = call i32() @pop()\n")
                    out.write(f"  %c{c} = shl i32 %b{c}, %a{c}\n")
                    out.write(f"  call void(i32) @push(i32 %c{c})\n")
                    c += 1
                elif word.operand == Intrinsic.SHR:
                    out.write(f"  %a{c} = call i32() @pop()\n")
                    out.write(f"  %b{c} = call i32() @pop()\n")
                    out.write(f"  %c{c} = lshr i32 %b{c}, %a{c}\n")
                    out.write(f"  call void(i32) @push(i32 %c{c})\n")
                    c += 1
                elif word.operand == Intrinsic.DUP:
                    out.write(f"  %a{c} = call i32() @pop()\n")
                    out.write(f"  call void(i32) @push(i32 %a{c})\n")
                    out.write(f"  call void(i32) @push(i32 %a{c})\n")
                    c += 1
                elif word.operand == Intrinsic.DROP:
                    out.write(f"  call i32() @pop()\n")
                    c += 1
                elif word.operand == Intrinsic.PRINT:
                    out.write(f"  %a{c} = call i32() @pop()\n")
                    out.write(f"  call i32(i8*, ...) @printf(i8* %fmtptr, i32 %a{c})\n")
                    c += 1
                else:
                    assert False, f"Unknown Intrinsic {word}"
            else:
                assert False, f"Unknown Op Type {word}"

        out.write("  ret i32 0\n")
        out.write("}\n")

def compile_ll_to_bin(ll_path: str, bin_path: str):
    print(f"[INFO] Compiling `{ll_path}` to native binary")
    run_echoed(["clang", ll_path, "-o", bin_path])
    print(f"[INFO] Compiled source file to native binary at `{bin_path}`")

def repr_program(program: list[Word]):
    """Generate a pretty-printed string from a program"""
    return "[\n\t" + ",\n\t".join([str(i) for i in program]) + "\n]"

COMMANDS = ["com", "to-ll", "from-ll"]
def usage():
    """Print a message on proper usage of the collver command"""
    print("""
USAGE: [python3.10] collver.py <subcommand> <filename> [flags]
    Subcommands:
        com: Compile a source (.collver) file to a binary executable (using clang)
        to-ll: Compile a source (.collver) file to llvm assembly/IR (without calling clang)
        from-ll: Compile an llvm IR (.ll) file to a binary executable (using clang)
    Flags:
        -r: Automatically run executable after compiling (only applicable for `com` command)
    """[1:-5]) # Chop off the initial \n, the final \n, and the 4 spaces at the end

def main():
    if len(sys.argv) < 3:
        usage()
        print("ERROR: Not enough arguments provided", file=sys.stderr)
        sys.exit(1)
    else:
        command = sys.argv[1]
        if command not in COMMANDS:
            usage()
            print(f"ERROR: Unknown subcommand {command}", file=sys.stderr)
            sys.exit(1)
        src_path = sys.argv[2]
        exec_path = os.path.splitext(src_path)[0]
        ll_path = exec_path + ".ll"
    if command != "from-ll":
        try:
            toks = lex_file(src_path)
        except FileNotFoundError:
            print(f"ERROR: File `{os.path.basename(src_path)}` not found!", file=sys.stderr)
            sys.exit(1)

        program = parse_tokens_into_words(toks)
        # print(repr_program(program))
        crossreference_program(program)

        compile_program_to_ll(program, ll_path)
    if command in ("com", "from-ll"):
        compile_ll_to_bin(ll_path, exec_path)
        if not "/" in exec_path:
            exec_path = os.path.join(".", exec_path)
        if "-r" in sys.argv:
            print(f"[INFO] Running `{exec_path}`")
            subprocess.run([exec_path])

if __name__ == '__main__':
    main()
