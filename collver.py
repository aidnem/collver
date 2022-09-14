from dataclasses import dataclass
from enum import Enum, auto
from io import TextIOWrapper
from typing import Optional
import copy
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
    typ   : TT                   # Token type (word or different values)
    value : str | int            # Value (word str or int value)
    file  : str                  # File that the token originated in
    row   : int                  # Row that the token is on (0 indexed)
    col   : int                  # Row that the token is on (0 indexed)
    expanded_from: list['Token'] # List of macro name tokens that this token has been expanded from

class OT(Enum):
    """Operation Types of words"""
    PUSH_INT  = auto()
    KEYWORD   = auto()
    PROC_NAME = auto()
    PROC_CALL = auto()
    INTRINSIC = auto()

class Keyword(Enum):
    """Keywords (words that aren't Intrinsics)"""
    PROC = auto()
    IF   = auto()
    ELIF = auto()
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
    typ     : OT                                        # Type of token (for different syntaxes)
    operand : Optional[int | str | Intrinsic | Keyword] # Value or type of keyword/intrinsic
    tok     : Token                                     # Token that the word was derived from
    jmp     : Optional[int]                             # Jump location for control flow words

def pretty_loc(tok: Token) -> str:
    """Given a token, return a human-readable string containing its location"""
    return f"{tok.file}:{tok.row+1}:{tok.col+1}"

def compiler_error(tok: Token, msg: str) -> None:
    """Print an error at a location, DOES NOT EXIT AUTOMATICALLY"""
    print(f"{pretty_loc(tok)}:ERROR: {msg}", file=sys.stderr)

def compiler_note(tok: Token, msg: str) -> None:
    """Print a note at a location, DOES NOT EXIT AUTOMATICALLY"""
    print(f"{pretty_loc(tok)}:NOTE: {msg}", file=sys.stderr)

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
                tok = Token(typ=typ, value=val, file=os.path.basename(file_path), row=row, col=col, expanded_from=[])
                toks.append(tok)
    return toks


assert len(Keyword) == 6, "Exhaustive map of Words in STR_TO_KEYWORD"
STR_TO_KEYWORD: dict[str, Keyword] = {
    "proc": Keyword.PROC,
    "if": Keyword.IF,
    "elif": Keyword.ELIF,
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

def extract_macros(tokens: list[Token]) -> tuple[dict[str, list[Token]], list[Token]]:
    """Extract macro definitions and return the defined macros and new tokens"""
    rtokens = list(reversed(tokens))
    macros: dict[str, list[Token]] = {}
    new_tokens: list[Token] = []
    while len(rtokens):
        tok = rtokens.pop()
        if tok.typ == TT.WORD and tok.value == "macro":
            if len(rtokens):
                name_tok = rtokens.pop()
            else:
                compiler_error(tok, "Malformed macro definition")
                sys.exit(1)

            if name_tok.typ != TT.WORD:
                compiler_error(name_tok, "Expected token of type `word` for macro name")
                sys.exit(1)


            body_toks = []
            body_tok: Optional[Token] = None
            while len(rtokens):
                body_tok = rtokens.pop()
                if body_tok.typ == TT.WORD and body_tok.value == "end":
                    break
                if body_tok.typ == TT.WORD and body_tok.value == name_tok.value:
                    compiler_error(body_tok, f"Recursive definition of macro `{name_tok.value}`")
                body_toks.append(body_tok)

            if body_tok is None:
                compiler_error(name_tok, "Expected macro body or `end` word, found EOF")
                sys.exit(1)
            elif body_tok.typ != TT.WORD or body_tok.value != "end":
                compiler_error(body_tok, "Expected `end` word to close macro definition, found EOF")
                sys.exit(1)

            assert type(name_tok.value) == str, "`word` token with non-str value"
            macros[str(name_tok.value)] = body_toks
        else:
            new_tokens.append(tok)

    return macros, new_tokens

def check_macros(macros: dict[str, list[Token]], tokens: list[Token]) -> bool:
    """Check whether or not a series of tokens contains any un-expanded macro references"""
    for tok in tokens:
        if tok.typ == TT.WORD and tok.value in macros:
            return True

    return False

def expand_macros(macros: dict[str, list[Token]], tokens: list[Token]) -> list[Token]:
    """Expand references to macros and return the new, expanded set of tokens"""
    new_tokens: list[Token] = []
    for token in tokens:
        if token.typ == TT.WORD and token.value in macros:
            expanded = copy.deepcopy(macros[token.value])
            for etok in token.expanded_from:
                if token.file == etok.file and token.row == etok.row and token.file == etok.file:
                    compiler_error(token, "Cyclic macro reference")
                    for etok in token.expanded_from:
                        compiler_note(etok, "Expanded from here")
                    sys.exit(1)

            for tok in expanded:
                tok.expanded_from.append(token)
                tok.expanded_from.extend(token.expanded_from)
            new_tokens.extend(expanded)
        else:
            new_tokens.append(token)

    return new_tokens


def preprocess_macros(tokens: list[Token]) -> list[Token]:
    """Given a list of tokens, extract macro definitions and expand macro references"""
    macros: dict[str, list[Token]] = {}
    macros, tokens = extract_macros(tokens)
    c = 0
    while check_macros(macros, tokens) and c < 10:
        tokens = expand_macros(macros, tokens)
        c += 1
    return tokens

@dataclass
class Program:
    """A program in intermediate representation"""
    file_path: str
    procs: dict[str, list[Word]]

def parse_tokens_into_words(tokens: list[Token]) -> list[Word]:
    """Given a list of tokens, convert them into compile-able words"""
    assert len(OT) == 5, "Exhaustive handling of Op Types in parse_tokens_into_words()"
    rtokens = list(reversed(tokens))
    words: list[Word] = []
    proc_names: list[str] = []
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
            elif words[-1].operand == Keyword.PROC:
                if tok.typ == TT.WORD:
                    words.append(Word(OT.PROC_NAME, tok.value, tok, None))
                    proc_names.append(str(tok.value))
                else:
                    compiler_error(tok, "Expected name of proc")
                    sys.exit(1)
            elif tok.value in proc_names:
                    words.append(Word(OT.PROC_CALL, tok.value, tok, None))
            else:
                compiler_error(tok, f"Unknown word `{tok.value}`")
                sys.exit(1)
        else:
            assert False, f"Unkown token type {tok.typ}"

    return words

assert len(Keyword) == 6, "Exhaustive list of control flow words for BLOCK_STARTERS"
BLOCK_STARTERS: list[Keyword] = [
    Keyword.IF,
]
def parse_words_into_program(file_path: str, words: list[Word]) -> Program:
    """Parse a series of words into a Program() object"""
    program = Program(file_path, {})
    rwords = list(reversed(words))
    buf: list[Word] = []
    nesting_depth = 0
    while len(rwords):
        word = rwords.pop()
        if word.operand != Keyword.PROC:
            print(word)
            compiler_error(word.tok, f"Expected `proc` keyword")
            sys.exit(1)
        if len(rwords):
            name_word = rwords.pop()
            assert name_word.typ == OT.PROC_NAME, "`proc` keyword followed by non-proc_name word (compiler bug)"
        else:
            compiler_error(word.tok, f"Expected name of proc, found nothing")
            sys.exit(1)

        while len(rwords):
            word = rwords.pop()
            if word.typ == OT.KEYWORD and word.operand in BLOCK_STARTERS:
                nesting_depth += 1
            elif word.typ == OT.KEYWORD and word.operand == Keyword.END:
                if nesting_depth:
                    nesting_depth -= 1
                else:
                    break
            buf.append(word)

        if word.operand != Keyword.END:
            compiler_error(word.tok, f"Expected `end` keyword at end of proc, found nothing")
            sys.exit(1)

        program.procs[str(name_word.operand)] = buf
        buf = []

    return program


def crossreference_proc(program: list[Word]) -> None:
    """Given a set of words, set the correct index to jump to for control flow words"""
    assert len(OT) == 5, "Exhaustive handling of Op Types in crossreference_proc()"
    assert len(Intrinsic) == 10, "Exhaustive handling of Intrincics in crossreference_proc()"
    assert len(Keyword) == 6, "Exhaustive handling of Keywords in crossreference_proc()"
    stack: list[int] = []
    for ip, word in enumerate(program):
        if word.typ == OT.KEYWORD:
            if word.operand == Keyword.IF:
                stack.append(ip)
            elif word.operand == Keyword.ELIF:
                try:
                    do_ip = stack.pop()
                    start_ip = stack.pop()
                except IndexError:
                    compiler_error(word.tok, "Word `elif` with no start of block")
                    sys.exit(1)

                start_word = program[start_ip]
                if start_word.operand == Keyword.IF:
                    program[do_ip].jmp = ip
                elif start_word.operand == Keyword.ELIF:
                    program[do_ip].jmp = ip
                    start_word.jmp = ip # Make the elif's jump to each other to skip if true
                else:
                    compiler_error(word.tok, "Word `elif` can only close `(el)if ... do` block")
                    sys.exit(1)

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
                if start_word.operand == Keyword.IF or start_word.operand == Keyword.ELIF:
                    word.jmp = ip
                else:
                    compiler_error(word.tok, "Word `else` can only close `(el)if ... do` block")
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
                elif start_word.operand == Keyword.ELIF:
                    print("I found it")
                    word.jmp = ip
                    start_word.jmp = ip
                else:
                    compiler_error(word.tok, "Word `end` can only close `(el)if ... do` block")
                    sys.exit(1)

                program[do_ip].jmp = ip

    if len(stack) != 0:
      compiler_error(program[stack.pop()].tok, f"Unclosed block")
      print(stack)
      sys.exit(1)

def compile_push_pop_functions(out: TextIOWrapper):
    """Write the LLVM IR for the push and pop functions to an open()ed file"""
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

def compile_print_function(out: TextIOWrapper):
    """Write the LLVM IR for the print intrinsic word function to an open()ed file"""
    out.write("declare i32 @printf(i8*, ...)\n")
    out.write("@fmt = private unnamed_addr constant [4 x i8] c\"%i\\0A\\00\"\n")

def compile_proc_to_ll(out: TextIOWrapper, proc_name: str, words: list[Word]):
    """Write LLVM IR for a procedure to an open()ed file"""
    assert len(OT) == 5, "Exhaustive handling of Op Types in compile_proc_to_ll()"
    assert len(Intrinsic) == 10, "Exhaustive handling of Intrincics in compile_proc_to_ll()"
    assert len(Keyword) == 6, "Exhaustive handling of Keywords in compile_proc_to_ll()"
    out.write(f"define void @proc_{proc_name}() ")
    out.write("{\n")
    out.write("  %fmtptr = getelementptr [4 x i8], [4 x i8]* @fmt, i32 0, i32 0\n")
    c: int = 0 # counter for unique numbers
    for ip, word in enumerate(words):
        out.write(f"  ; {str(word)}\n")
        if word.typ == OT.PUSH_INT:
            assert type(word.operand) == int, "PUSH_INT word has non-int type"
            out.write(f"  call void(i32) @push(i32 {word.operand})\n")
        elif word.typ == OT.PROC_CALL:
            out.write(f"  call void() @proc_{word.operand}()\n")
        elif word.typ == OT.KEYWORD:
            if word.operand == Keyword.PROC:
                assert False, f"Word: {word} of type keyword:PROC allowed to reach compile_proc_to_ll()"
            if word.operand == Keyword.IF:
                pass
            elif word.operand == Keyword.ELIF:
                out.write(f"  br label %ls{ip}\n") # So that LLVM thinks the block is 'closed'
                out.write(f"ls{ip}:\n") # Label to jump to from previous (el)if
                out.write(f"  br label %ls{word.jmp}\n") # Jump to the end if we hit the elif
                out.write(f"l{ip}:\n") # Label to jump to from previous (el)if
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
                out.write(f"  br label %ls{ip}\n") # 'Close' the block for llvm
                out.write(f"ls{ip}:\n") # Skip label
            else:
                assert False, f"Unknown keyword {word}"
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

    out.write("  ret void\n")
    out.write("}\n")

def compile_main_function(out: TextIOWrapper):
    """Write LLVM IR for a main function (the entry point) to an open()ed file"""
    out.write("define i32 @main() {\n")
    out.write("  call void() @proc_main()\n")
    out.write("  ret i32 0\n")
    out.write("}\n")

def compile_program_to_ll(program: Program, out_file_path: str):
    """Compile a series of Words into an llvm IR file (.ll)"""
    print(f"[INFO] Generating {out_file_path}")
    with open(out_file_path, "w+") as out:
        compile_push_pop_functions(out)
        compile_print_function(out)
        found_main = False
        for proc_name in program.procs:
            if proc_name == "main":
                found_main = True
            else:
                print(proc_name, "HHH")
            compile_proc_to_ll(out, proc_name, program.procs[proc_name])

        if not found_main:
            err_tok = Token(TT.WORD, "", program.file_path, 0, 0, [])
            compiler_error(err_tok, "No entry point found (expected `proc main ...`)")
            sys.exit(1)
        else:
            compile_main_function(out)

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

        toks = preprocess_macros(toks)
        words = parse_tokens_into_words(toks)
        # print(repr_program(program))
        program: Program = parse_words_into_program(src_path, words)
        for proc in program.procs:
            crossreference_proc(program.procs[proc])
        for proc in program.procs:
            print(f"proc {proc}")
            print(repr_program(program.procs[proc]))
            print("end")

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
