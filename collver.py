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
    INT    = auto()
    STRING = auto()
    WORD   = auto()

@dataclass
class Token:
    typ   : TT                   # Token type (word or different values)
    value : str | int            # Value (word str or int value)
    file  : str                  # File that the token originated in
    row   : int                  # Row that the token is on (0 indexed)
    col   : int                  # Row that the token is on (0 indexed)

class OT(Enum):
    """Operation Types of words"""
    PUSH_INT    = auto()
    PUSH_STR    = auto()
    KEYWORD     = auto()
    MEMORY_NAME = auto()
    PUSH_MEMORY = auto()
    PROC_NAME   = auto()
    PROC_CALL   = auto()
    INTRINSIC   = auto()

class Keyword(Enum):
    """Keywords (words that aren't Intrinsics)"""
    MEMORY = auto()
    PROC   = auto()
    IF     = auto()
    ELIF   = auto()
    WHILE  = auto()
    DO     = auto()
    ELSE   = auto()
    END    = auto()

class Intrinsic(Enum):
    """Intrinsic words"""
    PLUS    = auto()
    MINUS   = auto()
    MULT    = auto()
    DIV     = auto()
    MOD     = auto()
    EQ      = auto()
    NE      = auto()
    GT      = auto()
    LT      = auto()
    GE      = auto()
    LE      = auto()
    SHL     = auto()
    SHR     = auto()
    DUP     = auto()
    DROP    = auto()
    PRINT   = auto()
    PUTS    = auto()
    STORE8  = auto()
    LOAD8   = auto()
    STORE64 = auto()
    LOAD64  = auto()

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
    in_str = False
    chunks: list[tuple[int, str]] = []
    for idx, c in enumerate(line):
        if in_str:
            if c == '"':
                buffer += c
                chunks.append((start_idx, buffer))
                buffer = ""
                in_str = False
            else:
                if buffer[-1] == "\\" and c == "n":
                    buffer += "0A"
                elif buffer[-1] == "\\" and c == "r":
                    buffer += "0D"
                else:
                    buffer += c
        else:
            if c == " " or c == "\n":
                if len(buffer) != 0:
                    chunks.append((start_idx, buffer))
                    buffer = ""
            elif c == '"':
                if len(buffer) == 0:
                    start_idx = idx
                    buffer = c
                    in_str = True
            elif c == "/" and buffer == "/":
                buffer = ""
                break
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
    assert len(TT) == 3, "Exhaustive handling of Token Types in lex_file()"
    toks: list[Token] = []
    with open(file_path, "r") as f:
        for (row, line) in enumerate(f.readlines()):
            for (col, string) in lex_line(line):
                try:
                    val: int|str = int(string)
                    typ = TT.INT
                except ValueError:
                    if string[0] == '"' and string[-1] == '"':
                        val = string[1:-1]
                        typ = TT.STRING
                    else:
                        val = string
                        typ = TT.WORD
                tok = Token(typ=typ, value=val, file=file_path, row=row, col=col)
                toks.append(tok)
    return toks


assert len(Keyword) == 8, "Exhaustive map of Words in STR_TO_KEYWORD"
STR_TO_KEYWORD: dict[str, Keyword] = {
    "memory": Keyword.MEMORY,
    "proc": Keyword.PROC,
    "if": Keyword.IF,
    "elif": Keyword.ELIF,
    "while": Keyword.WHILE,
    "do": Keyword.DO,
    "else": Keyword.ELSE,
    "end": Keyword.END,
}

assert len(Intrinsic) == 21, "Exhaustive map of Intrinsics in STR_TO_INTRINSIC"
STR_TO_INTRINSIC: dict[str, Intrinsic] = {
    "+": Intrinsic.PLUS,
    "-": Intrinsic.MINUS,
    "*": Intrinsic.MULT,
    "/": Intrinsic.DIV,
    "%": Intrinsic.MOD,
    "=": Intrinsic.EQ,
    "!=": Intrinsic.NE,
    ">": Intrinsic.GT,
    "<": Intrinsic.LT,
    ">=": Intrinsic.GE,
    "<=": Intrinsic.LE,
    "<<": Intrinsic.SHL,
    ">>": Intrinsic.SHR,
    "dup": Intrinsic.DUP,
    "drop": Intrinsic.DROP,
    "print": Intrinsic.PRINT,
    "puts": Intrinsic.PUTS,
    "!8": Intrinsic.STORE8,
    "@8": Intrinsic.LOAD8,
    "!64": Intrinsic.STORE64,
    "@64": Intrinsic.LOAD64,
}


def extract_consts(tokens: list[Token]) -> tuple[dict[str, int], list[Token]]:
    """Extract const definitions and return the defined consts and new tokens"""
    rtokens = list(reversed(tokens))
    consts: dict[str, int] = {}
    new_tokens: list[Token] = []
    offset: int = 0
    while len(rtokens):
        tok = rtokens.pop()
        if tok.typ == TT.WORD and tok.value == "const":
            if len(rtokens):
                name_tok = rtokens.pop()
            else:
                compiler_error(tok, "Malformed const definition")
                sys.exit(1)

            if name_tok.typ != TT.WORD:
                compiler_error(name_tok, "Expected token of type `word` for const name")
                sys.exit(1)

            body_stack: list[int] = []
            body_tok: Optional[Token] = None
            while len(rtokens):
                body_tok = rtokens.pop()
                if body_tok.typ == TT.WORD and body_tok.value == "end":
                    break
                if body_tok.typ == TT.WORD and body_tok.value in consts:
                    body_stack.append(consts[str(body_tok.value)])
                elif body_tok.typ == TT.INT:
                    body_stack.append(int(body_tok.value))
                elif body_tok.typ == TT.WORD and body_tok.value == "+":
                    a = body_stack.pop()
                    b = body_stack.pop()
                    c = a + b
                    body_stack.append(c)
                elif body_tok.typ == TT.WORD and body_tok.value == "-":
                    a = body_stack.pop()
                    b = body_stack.pop()
                    c = b - a
                    body_stack.append(c)
                elif body_tok.typ == TT.WORD and body_tok.value == "*":
                    a = body_stack.pop()
                    b = body_stack.pop()
                    c = a * b
                    body_stack.append(c)
                elif body_tok.typ == TT.WORD and body_tok.value == "offset":
                    a = body_stack.pop()
                    body_stack.append(offset)
                    offset += a
                elif body_tok.typ == TT.WORD and body_tok.value == "reset":
                    body_stack.append(offset)
                    offset = 0
                else:
                    compiler_error(body_tok, f"Unsupported word in const definition `{body_tok.value}`")
                    sys.exit(1)

            if body_tok is None:
                compiler_error(name_tok, "Expected const body or `end` word, found EOF")
                sys.exit(1)
            elif body_tok.typ != TT.WORD or body_tok.value != "end":
                compiler_error(body_tok, "Expected `end` word to close const definition, found EOF")
                sys.exit(1)

            if len(body_stack) > 1:
                compiler_error(name_tok, f"Const value expression evaluated to more than one value")
                sys.exit(1)
            elif len(body_stack) == 0:
                compiler_error(name_tok, f"Const value expression evaluated to 0 values")
                sys.exit(1)
            else:
                consts[str(name_tok.value)] = body_stack[0]
        else:
            new_tokens.append(tok)

    return consts, new_tokens

def replace_consts(consts: dict[str, int], tokens: list[Token]) -> list[Token]:
    """Replace references to consts with their values in a list of tokens"""
    rtokens = list(reversed(tokens))
    new_tokens = []
    while len(rtokens):
        tok = rtokens.pop()
        if tok.typ == TT.WORD and tok.value in consts:
            new_tok = Token(TT.INT, consts[str(tok.value)], tok.file, tok.row, tok.col)
            print(new_tok)
            new_tokens.append(new_tok)
        else:
            new_tokens.append(tok)
    return new_tokens

def preprocess_includes(tokens: list[Token], included_files: list[str]) -> list[Token]:
    """Given a list of tokens, extract `include`s and replace them with the contents of the included file"""
    rtokens = list(reversed(tokens))
    new_tokens = []
    while len(rtokens):
        tok = rtokens.pop()
        if tok.typ == TT.WORD and tok.value == "include":
            if len(rtokens):
                file_tok = rtokens.pop()
            else:
                compiler_error(tok, "Expected string (name of included file), found EOF")
                sys.exit(1)

            if file_tok.typ == TT.STRING:
                src_path = str(file_tok.value)
                if src_path in included_files:
                    continue

                included_files.append(src_path)
                try:
                    print(f"[INFO] Including file {src_path}")
                    included_toks = lex_file(src_path)
                except FileNotFoundError:
                    try:
                        this_folder = os.path.split(__file__)[0]
                        std_path = os.path.join(this_folder, "std", src_path)
                        src_path = std_path
                        included_toks = lex_file(src_path)
                    except FileNotFoundError:
                        compiler_error(file_tok, f"ERROR: Included file `{os.path.basename(src_path)}` not found!")
                        sys.exit(1)

                new_tokens.extend(included_toks)
            else:
                compiler_error(tok, "Name of included file must be a string")
                sys.exit(1)
        else:
            new_tokens.append(tok)

    if len(new_tokens) > len(tokens):
        new_tokens = preprocess_includes(new_tokens, included_files)
    return new_tokens

def preprocess_consts(tokens: list[Token]) -> list[Token]:
    """Given a list of tokens, extract const definitions and replace const references"""
    consts: dict[str, int] = {}
    consts, tokens = extract_consts(tokens)
    tokens = replace_consts(consts, tokens)

    return tokens

@dataclass
class Proc:
    """A procedure (with local memory)"""
    memories: dict[str, int]
    strings: dict[int, str]
    words: list[Word]

@dataclass
class Program:
    """A program in intermediate representation"""
    file_path: str
    procs: dict[str, Proc]
    memories: dict[str, int]

def parse_tokens_into_words(tokens: list[Token]) -> list[Word]:
    """Given a list of tokens, convert them into compile-able words"""
    assert len(OT) == 8, "Exhaustive handling of Op Types in parse_tokens_into_words()"
    rtokens = list(reversed(tokens))
    words: list[Word] = []
    proc_names: list[str] = []
    mem_names: list[str] = []
    while len(rtokens):
        tok = rtokens.pop()
        if tok.typ == TT.INT:
            assert isinstance(tok.value, int), "INT token had non-int value"
            words.append(Word(OT.PUSH_INT, tok.value, tok, None))
        elif tok.typ == TT.STRING:
            assert isinstance(tok.value, str), "STRING token had non-string value"
            words.append(Word(OT.PUSH_STR, tok.value, tok, None))
        elif tok.typ == TT.WORD:
            if tok.value in STR_TO_KEYWORD:
                words.append(Word(OT.KEYWORD, STR_TO_KEYWORD[str(tok.value)], tok, None))
            elif tok.value in STR_TO_INTRINSIC:
                words.append(Word(OT.INTRINSIC, STR_TO_INTRINSIC[str(tok.value)], tok, None))
            elif len(words) and words[-1].operand == Keyword.PROC:
                if tok.typ == TT.WORD:
                    words.append(Word(OT.PROC_NAME, tok.value, tok, None))
                    proc_names.append(str(tok.value))
                else:
                    compiler_error(tok, "Expected name of proc")
                    sys.exit(1)
            elif len(words) and words[-1].operand == Keyword.MEMORY:
                if tok.typ == TT.WORD:
                    words.append(Word(OT.MEMORY_NAME, tok.value, tok, None))
                    mem_names.append(str(tok.value))
                else:
                    compiler_error(tok, "Expected name of memory")
                    sys.exit(1)
            elif tok.value in proc_names:
                    words.append(Word(OT.PROC_CALL, tok.value, tok, None))
            elif tok.value in mem_names:
                    words.append(Word(OT.PUSH_MEMORY, tok.value, tok, None))
            else:
                compiler_error(tok, f"Unknown word `{tok.value}`")
                sys.exit(1)
        else:
            assert False, f"Unkown token type {tok.typ}"

    return words

assert len(Keyword) == 8, "Exhaustive list of control flow words for BLOCK_STARTERS"
BLOCK_STARTERS: list[Keyword] = [
    Keyword.IF,
    Keyword.WHILE,
]

def eval_memory_size(rwords: list[Word], name_word: Word) -> int:
    """Parse and evaluate a memory definition's body, returning the size"""
    body_stack: list[int] = []
    body_word: Optional[Word] = None
    while len(rwords):
        body_word = rwords.pop()
        if body_word.typ == OT.KEYWORD and body_word.operand == Keyword.END:
            break
        elif body_word.typ == OT.PUSH_INT:
            assert isinstance(body_word.operand, int), "PUSH_INT word with non-int operand"
            body_stack.append(int(body_word.operand))
        elif body_word.typ == OT.INTRINSIC and body_word.operand == Intrinsic.PLUS:
            a = body_stack.pop()
            b = body_stack.pop()
            c = a + b
            body_stack.append(c)
        elif body_word.typ == OT.INTRINSIC and body_word.operand == Intrinsic.MINUS:
            a = body_stack.pop()
            b = body_stack.pop()
            c = b - a
            body_stack.append(c)
        elif body_word.typ == OT.INTRINSIC and body_word.operand == Intrinsic.MULT:
            a = body_stack.pop()
            b = body_stack.pop()
            c = a * b
            body_stack.append(c)
        else:
            compiler_error(body_word.tok, f"Unsupported word in memory definition `{body_word}`")
            sys.exit(1)

    if body_word is None:
        compiler_error(name_word.tok, "Expected memory size definition body or `end` word, found EOF")
        sys.exit(1)
    elif body_word.typ != OT.KEYWORD or body_word.operand != Keyword.END:
        compiler_error(body_word.tok, "Expected `end` word to close memory definition, found EOF")
        sys.exit(1)

    if len(body_stack) > 1:
        compiler_error(name_word.tok, f"Memory size expression evaluated to more than one value")
        sys.exit(1)
    elif len(body_stack) == 0:
        compiler_error(name_word.tok, f"Memory size expression evaluated to 0 values")
        sys.exit(1)

    return body_stack[0]

def get_strings(words: list[Word]) -> dict[int, str]:
    """Given a sequence of words (the body of a `proc`), return the locations and values of all string literals within"""
    strings: dict[int, str] = {}
    for ip, word in enumerate(words):
        if word.typ == OT.PUSH_STR:
            assert isinstance(word.operand, str), "PUSH_STR word with non-str operand"
            strings[ip] = word.operand

    return strings

def parse_words_into_program(file_path: str, words: list[Word]) -> Program:
    """Parse a series of words into a Program() object"""
    program = Program(file_path, {}, {})
    rwords = list(reversed(words))
    word_buf: list[Word] = []
    mem_buf: dict[str, int] = {}
    nesting_depth = 0
    while len(rwords):
        word = rwords.pop()
        if word.typ == OT.KEYWORD and word.operand == Keyword.PROC:
            if len(rwords):
                name_word = rwords.pop()
                assert name_word.typ == OT.PROC_NAME, "`proc` keyword followed by non-proc_name word (compiler bug)"
            else:
                compiler_error(word.tok, f"Expected name of proc, found nothing")
                sys.exit(1)

            while len(rwords):
                word = rwords.pop()
                if word.typ == OT.KEYWORD and word.operand == Keyword.MEMORY:
                    if len(rwords):
                        mem_name_word = rwords.pop()
                    else:
                        compiler_error(word.tok, "Expected name of memory, found nothing")
                        sys.exit(1)

                    mem_name = str(mem_name_word.operand)

                    mem_buf[mem_name] = eval_memory_size(rwords, mem_name_word)
                else:
                    rwords.append(word)
                    break

            while len(rwords):
                word = rwords.pop()
                if word.typ == OT.KEYWORD and word.operand in BLOCK_STARTERS:
                    nesting_depth += 1
                elif word.typ == OT.KEYWORD and word.operand == Keyword.END:
                    if nesting_depth:
                        nesting_depth -= 1
                    else:
                        break
                word_buf.append(word)

            if word.operand != Keyword.END:
                compiler_error(word.tok, f"Expected `end` keyword at end of proc, found nothing")
                sys.exit(1)

            strings = get_strings(word_buf)
            program.procs[str(name_word.operand)] = Proc(mem_buf, strings, word_buf)
            word_buf = []
            mem_buf = {}
        elif word.typ == OT.KEYWORD and word.operand == Keyword.MEMORY:
            if len(rwords):
                mem_name_word = rwords.pop()
            else:
                compiler_error(word.tok, "Expected name of memory, found nothing")
                sys.exit(1)

            mem_name = str(mem_name_word.operand)

            mem_size: int = eval_memory_size(rwords, mem_name_word)
            print(f"<DEBUG> Found global memory {mem_name} of size {mem_size}")
            program.memories[mem_name] = mem_size
        else:
            compiler_error(word.tok, f"Expected `proc` or `memory` keywords")
            sys.exit(1)

    return program


def crossreference_proc(proc: Proc) -> None:
    """Given a set of words, set the correct index to jump to for control flow words"""
    assert len(OT) == 8, "Exhaustive handling of Op Types in crossreference_proc()"
    assert len(Intrinsic) == 21, "Exhaustive handling of Intrincics in crossreference_proc()"
    assert len(Keyword) == 8, "Exhaustive handling of Keywords in crossreference_proc()"
    stack: list[int] = []
    for ip, word in enumerate(proc.words):
        if word.typ == OT.KEYWORD:
            if word.operand == Keyword.IF:
                stack.append(ip)
            if word.operand == Keyword.WHILE:
                stack.append(ip)
            elif word.operand == Keyword.ELIF:
                try:
                    do_ip = stack.pop()
                    start_ip = stack.pop()
                except IndexError:
                    compiler_error(word.tok, "Word `elif` with no start of block")
                    sys.exit(1)

                start_word = proc.words[start_ip]
                if start_word.operand == Keyword.IF:
                    proc.words[do_ip].jmp = ip
                elif start_word.operand == Keyword.ELIF:
                    proc.words[do_ip].jmp = ip
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

                start_word = proc.words[start_ip]
                if start_word.operand == Keyword.IF or start_word.operand == Keyword.ELIF:
                    word.jmp = ip
                else:
                    compiler_error(word.tok, "Word `else` can only close `(el)if ... do` block")
                    sys.exit(1)

                proc.words[do_ip].jmp = ip

                stack.append(start_ip)
                stack.append(ip)
            elif word.operand == Keyword.END:
                try:
                    do_ip = stack.pop()
                    start_ip = stack.pop()
                except IndexError:
                    compiler_error(word.tok, "Word `end` with no start of block")
                    sys.exit(1)

                start_word = proc.words[start_ip]
                if start_word.operand == Keyword.IF:
                    word.jmp = ip
                elif start_word.operand == Keyword.ELIF:
                    word.jmp = ip
                    start_word.jmp = ip
                elif start_word.operand == Keyword.WHILE:
                    word.jmp = start_ip
                else:
                    compiler_error(word.tok, "Word `end` can only close `(el)if ... do` block")
                    sys.exit(1)

                proc.words[do_ip].jmp = ip

    if len(stack) != 0:
      compiler_error(proc.words[stack.pop()].tok, f"Unclosed block")
      sys.exit(1)

def compile_push_pop_functions(out: TextIOWrapper):
    """Write the LLVM IR for the push and pop functions to an open()ed file"""
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

def compile_print_function(out: TextIOWrapper):
    """Write the LLVM IR for the print intrinsic word function to an open()ed file"""
    out.write("declare i64 @printf(i8*, ...)\n")
    out.write("@fmt = private unnamed_addr constant [4 x i8] c\"%i\\0A\\00\"\n")

def compile_puts_function(out: TextIOWrapper):
    """Write the LLVM IR for the puts intrinsic word function to an open()ed file"""
    out.write("@intrinsic_puts_fmt = private unnamed_addr constant [3 x i8] c\"%s\\00\"\n")
    out.write("define void @intrinsic_puts(ptr %strptr) {\n")
    # out.write("  %fmtptr = getelementptr [4 x i8], [4 x i8]* @fmt, i64 0, i64 0\n")
    out.write(f"  call i64(i8*, ...) @printf(i8* @intrinsic_puts_fmt, ptr %strptr)\n")
    out.write(f"  ret void\n")
    out.write("}\n")
    # out.write("@fmt = private unnamed_addr constant [4 x i8] c\"%i\\0A\\00\"\n")

def compile_global_memories(out: TextIOWrapper, memories: dict[str, int]):
    """Write the LLVM IR for global memories to an open()ed file"""
    for memory in memories:
        mem_size = memories[memory]
        out.write(f"; global memory {memory} {mem_size}\n")
        out.write(f"@global_mem_{memory} = global [{mem_size} x i8] zeroinitializer\n") # Memories are in number of bytes

def escaped_strlen(val: str) -> int:
    """Given a string, calculate the length of it, counting \\0A/\\0D as one character"""
    rval = list(reversed(list(val)))
    res: int = 0
    while len(rval):
        c = rval.pop()
        if c == "\\":
            if len(rval) >= 2:
                a = rval.pop()
                b = rval.pop()
                if a == "0" and b in ("A", "B"):
                    res += 1
                else:
                    res += 2
        else:
            res += 1

    return res

def compile_string_literals_outer(out: TextIOWrapper, proc_name: str, strings: dict[int, str]):
    """Write the LLVM IR for string literals within a `proc` to an open()ed file"""
    for str_ip in strings:
        strvalue = strings[str_ip]
        rlen = escaped_strlen(strvalue)
        out.write(f"@str_{proc_name}_{str_ip} = private unnamed_addr constant [{rlen + 1} x i8] c\"{strvalue}\\00\"\n")

def compile_string_literals_inner(out: TextIOWrapper, proc_name: str, strings: dict[int, str]):
    """Write the LLVM IR for pointers to string literals within a `proc` to an open()ed file"""
    for str_ip in strings:
        out.write(f"  %strptr{str_ip} = ptrtoint ptr @str_{proc_name}_{str_ip} to i64\n")
        # out.write(f"  store ptr @str_{proc_name}_{str_ip}, ptr %strptr{str_ip}\n")
        # out.write(f"  %strptr{str_ip} = getelementptr inbounds [{strlen + 1} x i8], ptr %str_{str_ip}, i64 0, i64 0\n") # Get the first element
        # out.write(f"  store ptr @str_{proc_name}_{str_ip}, ptr %strptr{str_ip}\n") # Store the pointer to the string from outside in that pointer

def compile_proc_to_ll(out: TextIOWrapper, proc_name: str, proc: Proc, global_memories: dict[str, int]):
    """Write LLVM IR for a procedure to an open()ed file"""
    assert len(OT) == 8, "Exhaustive handling of Op Types in compile_proc_to_ll()"
    assert len(Intrinsic) == 21, "Exhaustive handling of Intrincics in compile_proc_to_ll()"
    assert len(Keyword) == 8, "Exhaustive handling of Keywords in compile_proc_to_ll()"
    compile_string_literals_outer(out, proc_name, proc.strings)
    out.write(f"define void @proc_{proc_name}() ")
    out.write("{\n")
    out.write("  %fmtptr = getelementptr [4 x i8], [4 x i8]* @fmt, i64 0, i64 0\n")
    compile_string_literals_inner(out, proc_name, proc.strings)
    for memory in proc.memories:
        mem_size = proc.memories[memory]
        out.write(f"  ; memory {memory} {mem_size}\n")
        out.write(f"  %mem_{memory} = alloca [{mem_size} x i8]\n") # Memories are in number of bytes

    c: int = 0 # counter for unique numbers
    for ip, word in enumerate(proc.words):
        out.write(f"  ; {str(word)}\n")
        if word.typ == OT.PUSH_INT:
            assert isinstance(word.operand, int), "PUSH_INT word has non-int type"
            out.write(f"  call void(i64) @push(i64 {word.operand})\n")
        elif word.typ == OT.PUSH_STR:
            # out.write(f"  %ptrto_str_{c} = ptrtoint ptr %strptr{ip} to i64\n") # Cast that pointer to an i64
            out.write(f"  call void(i64) @push(i64 %strptr{ip})\n") # Push that i64
        elif word.typ == OT.PROC_CALL:
            out.write(f"  call void() @proc_{word.operand}()\n")
        elif word.typ == OT.PUSH_MEMORY:
            memory = str(word.operand)
            if memory in proc.memories:
                out.write(f"  %ptrto_{memory}_{c} = ptrtoint [{proc.memories[memory]} x i8]* %mem_{memory} to i64\n")
                out.write(f"  call void(i64) @push(i64 %ptrto_{memory}_{c})\n")
                c += 1
            elif memory in global_memories:
                out.write(f"  %ptrto_{memory}_{c} = ptrtoint [{global_memories[memory]} x i8]* @global_mem_{memory} to i64\n")
                out.write(f"  call void(i64) @push(i64 %ptrto_{memory}_{c})\n")
                c += 1
            else:
                compiler_error(word.tok, f"Memory {memory} is not defined globally or in proc {proc_name}")
                sys.exit(1)
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
            elif word.operand == Keyword.WHILE:
                out.write(f"  br label %l{ip}\n") # So that LLVM thinks the block is 'closed'
                out.write(f"l{ip}:\n") # Label for the end to jump to
            elif word.operand == Keyword.DO:
                out.write(f"  %a{c} = call i64() @pop()\n")
                # Compare number with 0 (true if a{n} != 0)
                out.write(f"  %b{c} = icmp ne i64 %a{c}, 0\n")
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
                out.write(f"  %a{c} = call i64() @pop()\n")
                out.write(f"  %b{c} = call i64() @pop()\n")
                out.write(f"  %c{c} = add i64 %a{c}, %b{c}\n")
                out.write(f"  call void(i64) @push(i64 %c{c})\n")
                c += 1
            elif word.operand == Intrinsic.MINUS:
                out.write(f"  %a{c} = call i64() @pop()\n")
                out.write(f"  %b{c} = call i64() @pop()\n")
                out.write(f"  %c{c} = sub i64 %b{c}, %a{c}\n")
                out.write(f"  call void(i64) @push(i64 %c{c})\n")
                c += 1
            elif word.operand == Intrinsic.MULT:
                out.write(f"  %a{c} = call i64() @pop()\n")
                out.write(f"  %b{c} = call i64() @pop()\n")
                out.write(f"  %c{c} = mul i64 %a{c}, %b{c}\n")
                out.write(f"  call void(i64) @push(i64 %c{c})\n")
                c += 1
            elif word.operand == Intrinsic.DIV:
                out.write(f"  %a{c} = call i64() @pop()\n")
                out.write(f"  %b{c} = call i64() @pop()\n")
                out.write(f"  %c{c} = sdiv i64 %b{c}, %a{c}\n")
                out.write(f"  call void(i64) @push(i64 %c{c})\n")
                c += 1
            elif word.operand == Intrinsic.MOD:
                out.write(f"  %a{c} = call i64() @pop()\n")
                out.write(f"  %b{c} = call i64() @pop()\n")
                out.write(f"  %c{c} = srem i64 %b{c}, %a{c}\n")
                out.write(f"  call void(i64) @push(i64 %c{c})\n")
                c += 1
            elif word.operand == Intrinsic.EQ:
                out.write(f"  %a{c} = call i64() @pop()\n")
                out.write(f"  %b{c} = call i64() @pop()\n")
                out.write(f"  %c_i1{c} = icmp eq i64 %a{c}, %b{c}\n")
                out.write(f"  %c{c} = zext i1 %c_i1{c} to i64\n")
                out.write(f"  call void(i64) @push(i64 %c{c})\n")
                c += 1
            elif word.operand == Intrinsic.NE:
                out.write(f"  %a{c} = call i64() @pop()\n")
                out.write(f"  %b{c} = call i64() @pop()\n")
                out.write(f"  %c_i1{c} = icmp ne i64 %a{c}, %b{c}\n")
                out.write(f"  %c{c} = zext i1 %c_i1{c} to i64\n")
                out.write(f"  call void(i64) @push(i64 %c{c})\n")
                c += 1
            elif word.operand == Intrinsic.GT:
                out.write(f"  %a{c} = call i64() @pop()\n")
                out.write(f"  %b{c} = call i64() @pop()\n")
                out.write(f"  %c_i1{c} = icmp sgt i64 %b{c}, %a{c}\n")
                out.write(f"  %c{c} = zext i1 %c_i1{c} to i64\n")
                out.write(f"  call void(i64) @push(i64 %c{c})\n")
                c += 1
            elif word.operand == Intrinsic.LT:
                out.write(f"  %a{c} = call i64() @pop()\n")
                out.write(f"  %b{c} = call i64() @pop()\n")
                out.write(f"  %c_i1{c} = icmp slt i64 %b{c}, %a{c}\n")
                out.write(f"  %c{c} = zext i1 %c_i1{c} to i64\n")
                out.write(f"  call void(i64) @push(i64 %c{c})\n")
                c += 1
            elif word.operand == Intrinsic.GE:
                out.write(f"  %a{c} = call i64() @pop()\n")
                out.write(f"  %b{c} = call i64() @pop()\n")
                out.write(f"  %c_i1{c} = icmp sge i64 %b{c}, %a{c}\n")
                out.write(f"  %c{c} = zext i1 %c_i1{c} to i64\n")
                out.write(f"  call void(i64) @push(i64 %c{c})\n")
                c += 1
            elif word.operand == Intrinsic.LE:
                out.write(f"  %a{c} = call i64() @pop()\n")
                out.write(f"  %b{c} = call i64() @pop()\n")
                out.write(f"  %c_i1{c} = icmp sle i64 %b{c}, %a{c}\n")
                out.write(f"  %c{c} = zext i1 %c_i1{c} to i64\n")
                out.write(f"  call void(i64) @push(i64 %c{c})\n")
                c += 1
            elif word.operand == Intrinsic.SHL:
                out.write(f"  %a{c} = call i64() @pop()\n")
                out.write(f"  %b{c} = call i64() @pop()\n")
                out.write(f"  %c{c} = shl i64 %b{c}, %a{c}\n")
                out.write(f"  call void(i64) @push(i64 %c{c})\n")
                c += 1
            elif word.operand == Intrinsic.SHR:
                out.write(f"  %a{c} = call i64() @pop()\n")
                out.write(f"  %b{c} = call i64() @pop()\n")
                out.write(f"  %c{c} = lshr i64 %b{c}, %a{c}\n")
                out.write(f"  call void(i64) @push(i64 %c{c})\n")
                c += 1
            elif word.operand == Intrinsic.DUP:
                out.write(f"  %a{c} = call i64() @pop()\n")
                out.write(f"  call void(i64) @push(i64 %a{c})\n")
                out.write(f"  call void(i64) @push(i64 %a{c})\n")
                c += 1
            elif word.operand == Intrinsic.DROP:
                out.write(f"  call i64() @pop()\n")
                c += 1
            elif word.operand == Intrinsic.PRINT:
                out.write(f"  %a{c} = call i64() @pop()\n")
                out.write(f"  call i64(i8*, ...) @printf(i8* %fmtptr, i64 %a{c})\n")
                c += 1
            elif word.operand == Intrinsic.PUTS:
                out.write(f"  %str_int{c} = call i64() @pop()\n")
                out.write(f"  %str_ptr{c} = inttoptr i64 %str_int{c} to ptr\n")
                out.write(f"  call i32 @intrinsic_puts(ptr noundef %str_ptr{c})\n")
                c += 1
            elif word.operand == Intrinsic.STORE8: # int ptr ->
                out.write(f"  %ptr_int{c} = call i64() @pop()\n") # The pointer is on top of the stack
                out.write(f"  %a{c} = call i64() @pop()\n")
                out.write(f"  %a_trunc{c} = trunc i64 %a{c} to i8\n") # Chop it down to i8 size so we can write it to a single byte
                out.write(f"  %ptr_{c} = inttoptr i64 %ptr_int{c} to ptr\n")
                out.write(f"  store i8 %a_trunc{c}, ptr %ptr_{c}\n")
                c += 1
            elif word.operand == Intrinsic.LOAD8: # ptr -> int
                out.write(f"  %ptr_int{c} = call i64() @pop()\n") # -> The pointer
                out.write(f"  %ptr_{c} = inttoptr i64 %ptr_int{c} to ptr\n")
                out.write(f"  %c_i8{c} = load i8, ptr %ptr_{c}\n")
                out.write(f"  %c_i64{c} = sext i8 %c_i8{c} to i64\n")
                out.write(f"  call void(i64) @push(i64 %c_i64{c})\n")
                c += 1
            elif word.operand == Intrinsic.STORE64: # int ptr ->
                out.write(f"  %ptr_int{c} = call i64() @pop()\n") # The pointer is on top of the stack
                out.write(f"  %a{c} = call i64() @pop()\n")
                out.write(f"  %ptr_{c} = inttoptr i64 %ptr_int{c} to ptr\n")
                out.write(f"  store i64 %a{c}, ptr %ptr_{c}\n")
                c += 1
            elif word.operand == Intrinsic.LOAD64: # ptr -> int
                out.write(f"  %ptr_int{c} = call i64() @pop()\n") # -> The pointer
                out.write(f"  %ptr_{c} = inttoptr i64 %ptr_int{c} to ptr\n")
                out.write(f"  %c_i64{c} = load i64, ptr %ptr_{c}\n")
                # out.write(f"  %c_i64{c} = sext i8 %c_i8{c} to i64\n")
                out.write(f"  call void(i64) @push(i64 %c_i64{c})\n")
                c += 1
            else:
                assert False, f"Unknown Intrinsic {word}"
        else:
            assert False, f"Unknown Op Type {word}"

    out.write("  ret void\n")
    out.write("}\n")

def compile_main_function(out: TextIOWrapper):
    """Write LLVM IR for a main function (the entry point) to an open()ed file"""
    out.write("define i64 @main() {\n")
    out.write("  call void() @proc_main()\n")
    out.write("  ret i64 0\n")
    out.write("}\n")

def compile_program_to_ll(program: Program, out_file_path: str):
    """Compile a series of Words into an llvm IR file (.ll)"""
    print(f"[INFO] Generating {out_file_path}")
    with open(out_file_path, "w+") as out:
        compile_push_pop_functions(out)
        compile_print_function(out)
        compile_puts_function(out)
        compile_global_memories(out, program.memories)
        found_main = False
        for proc_name in program.procs:
            if proc_name == "main":
                found_main = True
            compile_proc_to_ll(out, proc_name, program.procs[proc_name], program.memories)

        if not found_main:
            err_tok = Token(TT.WORD, "", program.file_path, 0, 0)
            compiler_error(err_tok, "No entry point found (expected `proc main ...`)")
            sys.exit(1)
        else:
            compile_main_function(out)

def compile_ll_to_bin(ll_path: str, bin_path: str):
    print(f"[INFO] Compiling `{ll_path}` to native binary")
    run_echoed(["llc", ll_path, "-o", bin_path + ".s", "-opaque-pointers"]) # -opaque-pointers argument because newer LLVm versions use [type]* instead of `ptr` type
    run_echoed(["clang", bin_path + ".s", "-o", bin_path])
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
            print(f"[INFO] Compiling file {src_path}")
            toks = lex_file(src_path)
        except FileNotFoundError:
            print(f"ERROR: File `{os.path.basename(src_path)}` not found!", file=sys.stderr)
            sys.exit(1)

        toks = preprocess_includes(toks, [])
        toks = preprocess_consts(toks)
        words = parse_tokens_into_words(toks)
        # print(repr_program(program))
        program: Program = parse_words_into_program(src_path, words)
        for proc in program.procs:
            crossreference_proc(program.procs[proc])
        # for proc in program.procs:
        #     print(f"proc {proc}")
        #     print(repr_program(program.procs[proc]))
        #     print("end")

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
