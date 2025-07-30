from __future__ import annotations


from dataclasses import astuple, dataclass
from enum import Enum, auto
from io import TextIOWrapper
from typing import Optional
import subprocess
import os
import sys


def run_echoed(cmd: list[str]):
    print(f"[CMD] {' '.join(cmd)}")
    return subprocess.run(cmd)


class TT(Enum):
    INT = auto()
    STRING = auto()
    WORD = auto()


@dataclass
class Token:
    typ: TT  # Token type (word or different values)
    value: str | int  # Value (word str or int value)
    file: str  # File that the token originated in
    row: int  # Row that the token is on (0 indexed)
    col: int  # Row that the token is on (0 indexed)


class OT(Enum):
    """Operation Types of words"""

    PUSH_INT = auto()
    PUSH_STR = auto()
    KEYWORD = auto()
    DATA_TYPE = auto()
    MEMORY_NAME = auto()
    PUSH_MEMORY = auto()
    PROC_NAME = auto()
    PROC_CALL = auto()
    INTRINSIC = auto()


class Keyword(Enum):
    """Keywords (words that affect control flow)"""

    MEMORY = auto()
    PROC = auto()
    EXTERN = auto()
    ARROW = auto()
    IF = auto()
    ELIF = auto()
    WHILE = auto()
    DO = auto()
    ELSE = auto()
    END = auto()


class DT(Enum):
    """Data type in collver"""

    INT = auto()
    """Any value that isn't a pointer"""
    STR = auto()
    """A special kind of pointer to the beginning of a null-terminated string"""
    PTR = auto()
    """A pointer to anything that isn't a string"""
    UNK = auto()
    """A type that has yet to be determined by the compiler"""


TypeAnnotation = tuple[DT, Token]

assert len(DT) == 4, "Exhaustive handling of DataTypes in STR_TO_DATATYPE"
STR_TO_DATATYPE: dict[str, DT] = {
    "int": DT.INT,
    "str": DT.STR,
    "ptr": DT.PTR,
    "unknown": DT.UNK,
}


assert len(DT) == 4, "Exhaustive handling of DataTypes in DATATYPE_TO_STR"
DATATYPE_TO_STR: dict[DT, str] = {
    DT.INT: "int",
    DT.STR: "str",
    DT.PTR: "ptr",
    DT.UNK: "unknown",
}


def try_parse_datatype(word: str) -> DT | None:
    """Try parsing a string into a data type, returning None if it is invalid"""

    # If it's a primitive, return it
    if word in STR_TO_DATATYPE:
        return STR_TO_DATATYPE[word]

    # Otherwise, not a data type
    return None


@dataclass
class Word:
    """A word (instruction) in Collver"""

    typ: OT  # Type of token (for different syntaxes)
    operand: Optional[int | str | Keyword | DT]  # Value or type of keyword/intrinsic
    tok: Token  # Token that the word was derived from
    jmp: Optional[int]  # Jump location for control flow words

    def __repr__(self) -> str:
        out = f"<{self.typ}"
        if self.operand is not None:
            out += " on " + str(self.operand)
        if self.jmp is not None:
            out += " to " + str(self.jmp)
        out += ">"
        return out


def pretty_loc(tok: Token) -> str:
    """Given a token, return a human-readable string containing its location"""
    return f"{tok.file}:{tok.row + 1}:{tok.col + 1}"


def compiler_warning(tok: Token, msg: str) -> None:
    """Print a warning at a location, DOES NOT EXIT AUTOMATICALLY"""
    print(f"{pretty_loc(tok)}:warning: {msg}", file=sys.stderr)


def compiler_error(tok: Token, msg: str) -> None:
    """Print an error at a location, DOES NOT EXIT AUTOMATICALLY"""
    print(f"{pretty_loc(tok)}:error: {msg}", file=sys.stderr)


def compiler_note(tok: Token, msg: str) -> None:
    """Print a note at a location, DOES NOT EXIT AUTOMATICALLY"""
    print(f"{pretty_loc(tok)}:note: {msg}", file=sys.stderr)


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
        for row, line in enumerate(f.readlines()):
            for col, string in lex_line(line):
                try:
                    val: int | str = int(string)
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


assert len(Keyword) == 10, "Exhaustive map of Words in STR_TO_KEYWORD"
STR_TO_KEYWORD: dict[str, Keyword] = {
    "memory": Keyword.MEMORY,
    "proc": Keyword.PROC,
    "extern": Keyword.EXTERN,
    "->": Keyword.ARROW,
    "if": Keyword.IF,
    "elif": Keyword.ELIF,
    "while": Keyword.WHILE,
    "do": Keyword.DO,
    "else": Keyword.ELSE,
    "end": Keyword.END,
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
                    compiler_error(
                        body_tok,
                        f"Unsupported word in const definition `{body_tok.value}`",
                    )
                    sys.exit(1)

            if body_tok is None:
                compiler_error(name_tok, "Expected const body or `end` word, found EOF")
                sys.exit(1)
            elif body_tok.typ != TT.WORD or body_tok.value != "end":
                compiler_error(
                    body_tok, "Expected `end` word to close const definition, found EOF"
                )
                sys.exit(1)

            if len(body_stack) > 1:
                compiler_error(
                    name_tok, f"Const value expression evaluated to more than one value"
                )
                sys.exit(1)
            elif len(body_stack) == 0:
                compiler_error(
                    name_tok, f"Const value expression evaluated to 0 values"
                )
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
                compiler_error(
                    tok, "Expected string (name of included file), found EOF"
                )
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
                        compiler_error(
                            file_tok,
                            f" Included file `{os.path.basename(src_path)}` not found!",
                        )
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


def extract_aliases(tokens: list[Token]) -> tuple[dict[str, Token], list[Token]]:
    rtokens = list(reversed(tokens))
    aliases: dict[str, Token] = {}
    new_toks: list[Token] = []

    while len(rtokens):
        tok = rtokens.pop()
        if tok.typ == TT.WORD and tok.value == "alias":
            if len(rtokens):
                name_tok = rtokens.pop()
            else:
                compiler_error(tok, "Expected name of alias, found EOF")
                sys.exit(1)

            if name_tok.typ != TT.WORD:
                compiler_error(name_tok, "Expected token of type `word` for alias name")
                sys.exit(1)

            if len(rtokens):
                value_tok = rtokens.pop()
            else:
                compiler_error(tok, "Expected value of alias, found EOF")
                sys.exit(1)

            assert isinstance(name_tok.value, str), (
                "Token of type `word` with non-str type"
            )

            if len(rtokens):
                end_tok = rtokens.pop()
            else:
                compiler_error(
                    value_tok,
                    "Expected `end` keyword to close alias definition, found nothing",
                )
                sys.exit(1)

            if end_tok.typ == TT.WORD and end_tok.value == "end":
                aliases[name_tok.value] = value_tok
            else:
                compiler_error(
                    value_tok, "Expected `end` keyword to close alias definition"
                )
        else:
            new_toks.append(tok)

    return aliases, new_toks


def replace_aliases(aliases: dict[str, Token], tokens: list[Token]) -> list[Token]:
    """Replace references to aliases with their values in a list of tokens"""
    rtokens = list(reversed(tokens))
    new_tokens = []
    while len(rtokens):
        tok = rtokens.pop()
        if tok.typ == TT.WORD and tok.value in aliases:
            alias_tok = aliases[str(tok.value)]
            new_tok = Token(alias_tok.typ, alias_tok.value, tok.file, tok.row, tok.col)
            new_tokens.append(new_tok)
        else:
            new_tokens.append(tok)
    return new_tokens


def preprocess_aliases(tokens: list[Token]) -> list[Token]:
    """Given a list of tokens, extract alias definitions and replace alias references"""
    aliases: dict[str, Token] = {}
    aliases, tokens = extract_aliases(tokens)
    tokens = replace_aliases(aliases, tokens)

    return tokens


@dataclass
class ProcTypeSig:
    args: list[TypeAnnotation]
    returns: list[TypeAnnotation]
    # Keep track of the arrow token to have a location for type signatures that don't have any arguments or returns
    arrow_tok: Token

    # This is a cleaner and more type safe way than using __iter__
    def as_tuple(self) -> tuple[list[TypeAnnotation], list[TypeAnnotation]]:
        """Return type sig as a tuple of (args, returns)"""
        return (self.args, self.returns)

    def pretty_print(self) -> str:
        """Pretty-print type signature as `arg arg arg -> return return return`"""
        return (
            " ".join([DATATYPE_TO_STR[arg[0]] for arg in self.args])
            + " -> "
            + " ".join([DATATYPE_TO_STR[ret[0]] for ret in self.returns])
        )


@dataclass
class Proc:
    """A procedure (with local memory)"""

    proc_tok: Token
    memories: dict[str, int]
    type_sig: ProcTypeSig
    strings: dict[int, str]
    words: list[Word]

    def __repr__(self) -> str:
        return f"Proc(\n  T: {self.type_sig.pretty_print()}\n  M: {self.memories}\n  S: {self.strings}\n  W: {self.words}\n  )"


@dataclass
class Program:
    """A program in intermediate representation"""

    file_path: str
    procs: dict[str, Proc]
    # Externs can be overloaded to allow for type-safe pointer math
    # E.g.
    #   int + int -> int, but ptr + int -> ptr
    externs: dict[str, list[ProcTypeSig]]
    memories: dict[str, int]


def parse_tokens_into_words(tokens: list[Token]) -> list[Word]:
    """Given a list of tokens, convert them into compile-able words"""
    assert len(OT) == 9, "Exhaustive handling of Op Types in parse_tokens_into_words()"
    rtokens = list(reversed(tokens))
    words: list[Word] = []
    proc_names: list[str] = []
    extern_names: list[str] = []
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
                words.append(
                    Word(OT.KEYWORD, STR_TO_KEYWORD[str(tok.value)], tok, None)
                )
            elif (
                isinstance(tok.value, str)
                and (vt := try_parse_datatype(tok.value)) is not None
            ):
                words.append(Word(OT.DATA_TYPE, vt, tok, None))
            elif tok.value == "here":
                words.append(Word(OT.PUSH_STR, pretty_loc(tok), tok, None))
            elif len(words) and words[-1].operand == Keyword.PROC:
                if tok.typ == TT.WORD:
                    words.append(Word(OT.PROC_NAME, tok.value, tok, None))
                    proc_names.append(str(tok.value))
                else:
                    compiler_error(tok, "Expected name of proc")
                    sys.exit(1)
            elif len(words) and words[-1].operand == Keyword.EXTERN:
                if tok.typ == TT.WORD:
                    words.append(Word(OT.PROC_NAME, tok.value, tok, None))
                    extern_names.append(str(tok.value))
                else:
                    compiler_error(tok, "Expected name of extern")
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
            elif tok.value in extern_names:
                words.append(Word(OT.PROC_CALL, tok.value, tok, None))
            elif tok.value in mem_names:
                words.append(Word(OT.PUSH_MEMORY, tok.value, tok, None))
            else:
                compiler_error(tok, f"Unknown word `{tok.value}`")
                compiler_note(
                    tok,
                    "Externs can no longer be inferred due to typechecking as of 07-29-2025",
                )
                sys.exit(1)
        else:
            assert False, f"Unkown token type {tok.typ}"

    return words


assert len(Keyword) == 10, "Exhaustive list of control flow words for BLOCK_STARTERS"
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
            assert isinstance(body_word.operand, int), (
                "PUSH_INT word with non-int operand"
            )
            body_stack.append(int(body_word.operand))
        elif body_word.typ == OT.PROC_CALL and body_word.operand == "intrinsic_plus":
            a = body_stack.pop()
            b = body_stack.pop()
            c = a + b
            body_stack.append(c)
        elif body_word.typ == OT.PROC_CALL and body_word.operand == "intrinsic_minus":
            a = body_stack.pop()
            b = body_stack.pop()
            c = b - a
            body_stack.append(c)
        elif body_word.typ == OT.PROC_CALL and body_word.operand == "intrinsic_mult":
            a = body_stack.pop()
            b = body_stack.pop()
            c = a * b
            body_stack.append(c)
        else:
            compiler_error(
                body_word.tok, f"Unsupported word in memory definition `{body_word}`"
            )
            sys.exit(1)

    if body_word is None:
        compiler_error(
            name_word.tok,
            "Expected memory size definition body or `end` word, found EOF",
        )
        sys.exit(1)
    elif body_word.typ != OT.KEYWORD or body_word.operand != Keyword.END:
        compiler_error(
            body_word.tok, "Expected `end` word to close memory definition, found EOF"
        )
        sys.exit(1)

    if len(body_stack) > 1:
        compiler_error(
            name_word.tok, f"Memory size expression evaluated to more than one value"
        )
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


def parse_proc_type_sig(
    proc_name_word: Word, rwords: list[Word], is_extern: bool = False
) -> ProcTypeSig:
    types_in_buf: list[TypeAnnotation] = []
    types_out_buf: list[TypeAnnotation] = []

    # Initialize word to avoid possibly unbound issues
    word: Word = proc_name_word

    if len(rwords) == 0:
        compiler_error(
            proc_name_word.tok,
            f"Expected a data type or `->` keyword, found EOF",
        )
        sys.exit(1)

    while len(rwords):
        word = rwords.pop()

        if word.typ == OT.DATA_TYPE and type(word.operand) is DT:
            types_in_buf.append((word.operand, word.tok))
        elif word.typ == OT.KEYWORD and word.operand == Keyword.ARROW:
            break
        else:
            compiler_error(
                word.tok,
                f"Expected a data type or `->` keyword, found `{word.operand}`",
            )

    if word.operand != Keyword.ARROW:
        compiler_error(
            word.tok,
            f"Expected `->` keyword at end of proc argument type signature, found nothing",
        )
        sys.exit(1)

    arrow_tok = word.tok

    while len(rwords):
        word = rwords.pop()

        if word.typ == OT.DATA_TYPE and type(word.operand) == DT:
            types_out_buf.append((word.operand, word.tok))
        elif word.typ == OT.KEYWORD and (
            (not is_extern and word.operand == Keyword.DO)
            or (is_extern and word.operand == Keyword.END)
        ):
            break
        else:
            if is_extern:
                compiler_error(
                    word.tok,
                    f"Expected a data type or `do` keyword, found `{word.operand}`",
                )
            else:
                compiler_error(
                    word.tok,
                    f"Expected a data type or `end` keyword, found `{word.operand}`",
                )
            sys.exit(1)

    if not is_extern and word.operand != Keyword.DO:
        compiler_error(
            word.tok,
            f"Expected `do` keyword at end of proc type signature, found nothing",
        )
        sys.exit(1)

    if is_extern and word.operand != Keyword.END:
        compiler_error(
            word.tok,
            f"Expected `end` keyword at end of extern type signature, found nothing",
        )
        sys.exit(1)

    return ProcTypeSig(types_in_buf, types_out_buf, arrow_tok)


def parse_words_into_program(file_path: str, words: list[Word]) -> Program:
    """Parse a series of words into a Program() object"""
    program = Program(file_path, {}, {}, {})
    rwords = list(reversed(words))
    word_buf: list[Word] = []
    mem_buf: dict[str, int] = {}
    nesting_depth = 0
    while len(rwords):
        word = rwords.pop()
        if word.typ == OT.KEYWORD and word.operand == Keyword.PROC:
            proc_tok = word.tok
            if len(rwords):
                name_word = rwords.pop()
                assert name_word.typ == OT.PROC_NAME, (
                    "`proc` keyword followed by non-proc_name word (compiler bug)"
                )
            else:
                compiler_error(word.tok, "Expected name of proc, found nothing")
                sys.exit(1)

            type_sig = parse_proc_type_sig(name_word, rwords)

            while len(rwords):
                word = rwords.pop()
                if word.typ == OT.KEYWORD and word.operand == Keyword.MEMORY:
                    if len(rwords):
                        extern_name_word = rwords.pop()
                    else:
                        compiler_error(
                            word.tok, "Expected name of memory, found nothing"
                        )
                        sys.exit(1)

                    extern_name = str(extern_name_word.operand)

                    mem_buf[extern_name] = eval_memory_size(rwords, extern_name_word)
                    continue
                elif word.typ == OT.KEYWORD and word.operand in BLOCK_STARTERS:
                    nesting_depth += 1
                elif word.typ == OT.KEYWORD and word.operand == Keyword.END:
                    if nesting_depth:
                        nesting_depth -= 1
                    else:
                        break
                word_buf.append(word)

            if word.operand != Keyword.END:
                compiler_error(
                    word.tok, f"Expected `end` keyword at end of proc, found nothing"
                )
                sys.exit(1)

            strings = get_strings(word_buf)
            program.procs[str(name_word.operand)] = Proc(
                proc_tok, mem_buf, type_sig, strings, word_buf
            )
            word_buf = []
            mem_buf = {}
        elif word.typ == OT.KEYWORD and word.operand == Keyword.MEMORY:
            if len(rwords):
                extern_name_word = rwords.pop()
            else:
                compiler_error(word.tok, "Expected name of memory, found nothing")
                sys.exit(1)

            extern_name = str(extern_name_word.operand)

            local_mem_size: int = eval_memory_size(rwords, extern_name_word)
            program.memories[extern_name] = local_mem_size
        elif word.typ == OT.KEYWORD and word.operand == Keyword.EXTERN:
            if len(rwords):
                extern_name_word = rwords.pop()
            else:
                compiler_error(word.tok, "Expected name of extern, found nothing")
                sys.exit(1)

            extern_name = str(extern_name_word.operand)

            type_sig = parse_proc_type_sig(extern_name_word, rwords, is_extern=True)

            # Create a new entry in the externs if it didn't previously exist
            if extern_name not in program.externs:
                program.externs[extern_name] = []

            # Then add this type signature to the list
            program.externs[extern_name].append(type_sig)
        else:
            compiler_error(word.tok, "Expected `proc` or `memory` keywords")
            sys.exit(1)

    return program


def test_proc_type_sig(
    proc_call: Word,
    type_sig: ProcTypeSig,
    type_stack: list[TypeAnnotation],
    should_error: bool = False,
) -> bool:
    """Test whether or not a procedure type signature matches the top items on the type stack."""
    arguments: list[TypeAnnotation]
    arguments, _ = type_sig.as_tuple()

    if len(arguments) > len(type_stack):
        if should_error:
            compiler_error(
                proc_call.tok,
                f"Expected {len(arguments)} arguments for procedure {proc_call.operand} but found only {len(type_stack)}",
            )
            sys.exit(1)
        return False

    rarguments = reversed(arguments)

    for idx, arg in enumerate(rarguments):
        # print(f"-> {-1-idx} in {type_stack}")
        # The type that actually exists, to be compared with expected argument
        actual_type = type_stack[-1 - idx]
        if actual_type[0] != arg[0]:
            if should_error:
                compiler_error(
                    proc_call.tok,
                    f"Expected {arg[0]} but found {actual_type[0]} as argument {len(arguments) - idx} of procedure {proc_call.operand}.",
                )
                compiler_note(actual_type[1], "Problematic type pushed here")
                compiler_note(arg[1], "Type signature defined here")
                sys.exit(1)
            return False

    return True


def apply_proc_type_sig(
    proc_call: Word, type_sig: ProcTypeSig, type_stack: list[TypeAnnotation]
):
    """
    Apply a procedure type signature (simulate running the procedure)

    This assumes that the type sig is possible. test_proc_type_sig() MUST return true before this is called.
    """
    assert test_proc_type_sig(proc_call, type_sig, type_stack), (
        "test_proc_type_sig not successful when apply_proc_type_sig was called (compiler bug)"
    )

    arguments: list[TypeAnnotation]
    returns: list[TypeAnnotation]

    arguments, returns = type_sig.as_tuple()

    for _ in arguments:
        _ = type_stack.pop()

    type_stack.extend(returns)


def dbg_type_stack(type_stack: list[TypeAnnotation]):
    print("Type stack")
    print("  == TOP == ")
    for dt, tok in reversed(type_stack):
        print(f"  {dt} from {pretty_loc(tok)}")
    print("  == BOTTOM == ")


class TypeDifference(Enum):
    NONE = auto()
    FIRST_LONGER = auto()
    SECOND_LONGER = auto()
    MISMATCH = auto()


def stacks_match(
    type_stack1: list[TypeAnnotation], type_stack2: list[TypeAnnotation]
) -> tuple[TypeDifference, tuple[Token, Token] | None]:
    if len(type_stack1) > len(type_stack2):
        return TypeDifference.FIRST_LONGER, None
    elif len(type_stack1) < len(type_stack2):
        return TypeDifference.SECOND_LONGER, None

    for a, b in zip(type_stack1, type_stack2):
        if a[0] != b[0]:
            return TypeDifference.MISMATCH, (a[1], b[1])

    return TypeDifference.NONE, None


def compiler_type_error(diff: TypeDifference, context: str, reason: str, tok1: Token|None, tok2: Token|None, stack1: list[TypeAnnotation], stack2: list[TypeAnnotation]):
    """
    Print a type error!
    """

    brief: str = ""
    if diff == TypeDifference.NONE:
        return
    elif diff == TypeDifference.FIRST_LONGER or diff == TypeDifference.SECOND_LONGER:
        brief = "Number of items on the stack changes."

    message = f"Type error in {context}: "
    pass


TypeStack = list[TypeAnnotation]


class BlockMarker(Enum):
    """
    Types of blocks that must have consistent typing

    These are signified by the start of the block, where the stack snapshot was pushed.
    For instance, an `if ... do ... end` would have:
        -             ^               : IF, [] pushed to signify an IF was passed
        -                    ^        : IF was popped and read, IF_DO pushed
        -                           ^ : IF_DO popped, used to verify that types weren't modified
    Similarly, `if ... do ... else ... end` would have:
        -       ^ IF, [] pushed to signify an IF was passed
        -              ^ IF popped and read, IF_DO pushed
        -                     ^ IF_DO popped (if-else has multiple branches, so original state is inconsequential) and ELSE pushed
        -                              ^ ELSE popped, snapshot is compared with current typestack state
    Just like `if ... do ... elif ... do ... elif ... do ... else ... end`
        -      ^ IF, [] pushed
        -             ^ IF popped, IF_DO pushed
        -                    ^ IF_DO popped and read, but then re-pushed because: until we know there is a final else, if-elif cannot modify types because there is no guarantee all branches will run
        -                    ^ ELIF pushed to verify condition is type-safe
        -                             ^ ELIF popped, compared to ensure that elif condition didn't modify stack (since it might not run, it cannot change stack types)
        -                             ^ ELIF_DO pushed, for comparison with next branch
        -                                    ^ ELIF_DO popped and compared with current stack state to ensure that the 2 branches had identical behavior. New ELIF pushed for condition verification.
        -                                             ^ ELIF popped and compared to ensure condition didn't modify stack state. ELIF_DO pushed to compare with next branch.
        -                                                    ^ ELIF_DO popped and compared with current state to make sure that the 2 branches had identical behavior.
        -                                                    ^ Because else was found, original IF_DO is popped: else guarantees that 1 branch will always run, so state can be modified as long as each branch is consistent.
        -                                                    ^ ELSE pushed for comparison at the very end
        -                                                             ^ ELSE popped, snapshot is compared with current typestack state to ensure that all branches behaved the same
    This one's a little different: `if ... do ... elif ... do ... end` cannot modify the types because there's no guarantee that any branch will run.
        -                           ^ IF, [] pushed
        -                                  ^ IF popped, IF_DO pushed
        -                                         ^ IF_DO popped and read, but then re-pushed because: until we know there is a final else, if-elif cannot modify types because there is no guarantee all branches will run
        -                                         ^ ELIF pushed to verify condition is type-safe
        -                                                  ^ ELIF popped, compared to ensure that elif condition didn't modify stack (since it might not run, it cannot change stack types)
        -                                                  ^ ELIF_DO pushed, for comparison with next branch
        -                                                         ^ ELIF_DO popped and compared with current state to make sure the 2 branches had identical behavior.
        -                                                         ^ Because ELIF_DO was found and not ELSE, the original IF_DO is also popped and compared to ensure that the branches didn't modify the types, since any branch not is guaranteed to run.
    """

    IF = auto()  # Pushed with an empty type stack to indicate that an IF was passed
    IF_DO = auto()
    IF_MULTIPLE = auto()
    ELIF = auto()
    ELIF_DO = auto()
    ELSE = auto()
    # TODO: support typechecking of while loops


def type_check_proc(name: str, proc: Proc, program: Program):
    """
    Typecheck a procedure

    Typechecking follows a few simple rules:
        - `if` statement conditions CAN modify the stack, because the first condition will always run. However, subsequent `elif ... do` conditions CANNOT since they may not run.
        - `if ... do ... end` statements cannot modify the stack because the body may not run
        - `if ... do ... elif ... do ... end` statements similarly cannot modify the stack because no branch's body is guaranteed to run
        - `if ... do ... else ... end` and `if ... do ... elif ... do ... else ... end` (etc.) CAN modify the stack, because one branch is always guaranteed to run. However, all branches must be identical.
        - `while` conditions cannot modify the stack, as the condition may run an unpredictable number of times.
        - `while ... do ... end` statement bodies may not modify the stack, as they may run an unpredictable number of times.
    """
    # print("Type checking proc " + name)
    # print(f"Type signature: {proc.type_sig.pretty_print()}")
    # print(f"Has {len(proc.words)} words")
    type_stack: TypeStack = []
    block_stack: list[tuple[BlockMarker, TypeStack]] = []
    arguments: list[TypeAnnotation]
    returns: list[TypeAnnotation]
    arguments, returns = proc.type_sig.as_tuple()
    for arg_type in arguments:
        type_stack.append(arg_type)

    # print("initialized type stack with arguments:")
    # dbg_type_stack(type_stack)

    for word in proc.words:
        # dbg_type_stack(type_stack)
        if word.typ == OT.PUSH_INT:
            type_stack.append((DT.INT, word.tok))
        elif word.typ == OT.PUSH_STR:
            type_stack.append((DT.STR, word.tok))
        elif word.typ == OT.PUSH_MEMORY:
            type_stack.append((DT.PTR, word.tok))
        elif word.typ == OT.PROC_CALL:
            if word.operand in program.procs:
                assert type(word.operand) is str, "Non-str operand of PROC_CALL word"
                proc_type_sig = program.procs[word.operand].type_sig
                if test_proc_type_sig(
                    word, proc_type_sig, type_stack, should_error=True
                ):
                    apply_proc_type_sig(word, proc_type_sig, type_stack)
                # This will exit if it fails, so no else is needed
            elif word.operand in program.externs:
                assert type(word.operand) is str, "Non-str operand of PROC_CALL word"
                type_sigs = program.externs[word.operand]

                found_match = False
                for type_sig in type_sigs:
                    if test_proc_type_sig(word, type_sig, type_stack):
                        found_match = True
                        apply_proc_type_sig(word, type_sig, type_stack)

                if not found_match:
                    compiler_error(
                        word.tok,
                        f"Incompatible types found for call to extern proc {word.operand}",
                    )
                    compiler_note(word.tok, "Expected one of:")
                    for type_sig in type_sigs:
                        compiler_note(
                            type_sig.arrow_tok,
                            f"defined here: {type_sig.pretty_print()}",
                        )
                    sys.exit(1)
            else:
                compiler_warning(
                    word.tok,
                    f"Proc call made to undefined proc {word.operand}, therefore proc {name} cannot be typechecked.",
                )
                compiler_note(
                    word.tok,
                    "Typechecking will continue as if the procedure was found to be safe.",
                )
                return
        elif word.typ == OT.KEYWORD and word.operand == Keyword.IF:
            block_stack.append((BlockMarker.IF, []))
        elif word.typ == OT.KEYWORD and word.operand == Keyword.DO:
            assert len(block_stack) >= 1, (
                "`do` keyword encountered in typechecking without start of block."
            )
            marker, snapshot = block_stack.pop()
            if marker == BlockMarker.IF:
                block_stack.append((BlockMarker.IF_DO, type_stack.copy()))
            elif marker == BlockMarker.ELIF:
                diff, toks = stacks_match(snapshot, type_stack)
                if diff != TypeDifference.NONE:
                    pass
        elif word.typ == OT.KEYWORD and word.operand in (
            Keyword.IF,
            Keyword.ELIF,
            Keyword.ELSE,
            Keyword.WHILE,
            Keyword.END,
        ):
            assert False, "Not implemented :("
        else:
            assert False, f"Word {word} not implemented"

    if len(returns) != len(type_stack):
        compiler_error(
            proc.proc_tok,
            f"Procedure supposed to return {len(returns)} values, actually returned {len(type_stack)}.",
        )
        compiler_note(
            proc.proc_tok,
            f"Expected {', '.join([str(r[0]) for r in returns])}, found {', '.join([str(t[0]) for t in type_stack])}",
        )
        if len(type_stack) > len(returns):
            for erroneous_type, loc in type_stack:
                compiler_note(loc, f"{erroneous_type} originated here")
        sys.exit(1)

    for ret, type_ann in zip(returns, type_stack):
        if ret[0] != type_ann[0]:
            compiler_error(
                proc.proc_tok,
                f"Expected {ret[0]} as return from procedure {name}, actually returned {type_ann[0]}.",
            )
            compiler_note(type_ann[1], "Incorrect type pushed here")
            compiler_note(ret[1], "Return type defined here")
            sys.exit(1)


def type_check_program(program: Program):
    """Typecheck a program"""
    for proc in program.procs:
        type_check_proc(proc, program.procs[proc], program)

    if "main" in program.procs:
        main_sig = program.procs["main"].type_sig
        if (
            len(main_sig.args) != 2
            or main_sig.args[0][0] != DT.INT
            or main_sig.args[1][0] != DT.PTR
            or len(main_sig.returns) != 1
            or main_sig.returns[0][0] != DT.INT
        ):
            compiler_error(
                main_sig.arrow_tok,
                "`main` proc must have type signature `int ptr -> int` for (int argc, char* argv) -> int returncode",
            )
            sys.exit(1)


def crossreference_proc(proc: Proc) -> None:
    """Given a set of words, set the correct index to jump to for control flow words"""
    assert len(OT) == 8, "Exhaustive handling of Op Types in crossreference_proc()"
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
                    start_word.jmp = (
                        ip  # Make the elif's jump to each other to skip if true
                    )
            else:
                compiler_error(
                    word.tok, "Word `elif` can only close `(el)if ... do` block"
                )
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
                compiler_error(
                    word.tok, "Word `else` can only close `(el)if ... do` block"
                )
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
                compiler_error(
                    word.tok,
                    "Word `end` can only close `(el)if ... do` or `while ... do` blocks",
                )
                sys.exit(1)

            proc.words[do_ip].jmp = ip
    if len(stack) != 0:
        compiler_error(proc.words[stack.pop()].tok, "Unclosed block")
        sys.exit(1)


def compile_push_pop_functions(out: TextIOWrapper):
    """Write the LLVM IR for the push and pop functions to an open()ed file"""
    out.write("declare void @push(i64)\n")
    out.write("declare i64 @pop()\n")


def compile_extern_procs(out: TextIOWrapper, procs: list[str]):
    """Write the LLVM IR for declaring external processes to an open()ed file"""
    for proc in procs:
        out.write(f"declare void @proc_{proc}()\n")


def compile_global_memories(out: TextIOWrapper, memories: dict[str, int]):
    """Write the LLVM IR for global memories to an open()ed file"""
    for memory in memories:
        mem_size = memories[memory]
        out.write(f"; global memory {memory} {mem_size}\n")
        out.write(
            f"@global_mem_{memory} = global [{mem_size} x i8] zeroinitializer\n"
        )  # Memories are in number of bytes


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
            res += len(c.encode())

    return res


def compile_string_literals_outer(
    out: TextIOWrapper, proc_name: str, strings: dict[int, str]
):
    """Write the LLVM IR for string literals within a `proc` to an open()ed file"""
    for str_ip in strings:
        strvalue = strings[str_ip]
        rlen = escaped_strlen(strvalue)
        out.write(
            f'@str_{proc_name}_{str_ip} = private unnamed_addr constant [{rlen + 1} x i8] c"{strvalue}\\00"\n'
        )


def compile_string_literals_inner(
    out: TextIOWrapper, proc_name: str, strings: dict[int, str]
):
    """Write the LLVM IR for pointers to string literals within a `proc` to an open()ed file"""
    for str_ip in strings:
        out.write(
            f"  %strptr{str_ip} = ptrtoint ptr @str_{proc_name}_{str_ip} to i64\n"
        )


def compile_proc_to_ll(
    out: TextIOWrapper, proc_name: str, proc: Proc, global_memories: dict[str, int]
):
    """Write LLVM IR for a procedure to an open()ed file"""
    assert len(OT) == 8, "Exhaustive handling of Op Types in compile_proc_to_ll()"
    assert len(Keyword) == 8, "Exhaustive handling of Keywords in compile_proc_to_ll()"
    compile_string_literals_outer(out, proc_name, proc.strings)
    out.write(f"define void @proc_{proc_name}() ")
    out.write("{\n")
    compile_string_literals_inner(out, proc_name, proc.strings)
    for memory in proc.memories:
        mem_size = proc.memories[memory]
        out.write(f"  ; memory {memory} {mem_size}\n")
        out.write(
            f"  %mem_{memory} = alloca [{mem_size} x i8]\n"
        )  # Memories are in number of bytes

    c: int = 0  # counter for unique numbers
    for ip, word in enumerate(proc.words):
        out.write(f"  ; {str(word)}\n")
        if word.typ == OT.PUSH_INT:
            assert isinstance(word.operand, int), "PUSH_INT word has non-int type"
            out.write(f"  call void(i64) @push(i64 {word.operand})\n")
        elif word.typ == OT.PUSH_STR:
            out.write(f"  call void(i64) @push(i64 %strptr{ip})\n")  # Push that i64
        elif word.typ == OT.PROC_CALL:
            out.write(f"  call void() @proc_{word.operand}()\n")
        elif word.typ == OT.PUSH_MEMORY:
            memory = str(word.operand)
            if memory in proc.memories:
                out.write(
                    f"  %ptrto_{memory}_{c} = ptrtoint [{proc.memories[memory]} x i8]* %mem_{memory} to i64\n"
                )
                out.write(f"  call void(i64) @push(i64 %ptrto_{memory}_{c})\n")
                c += 1
            elif memory in global_memories:
                out.write(
                    f"  %ptrto_{memory}_{c} = ptrtoint [{global_memories[memory]} x i8]* @global_mem_{memory} to i64\n"
                )
                out.write(f"  call void(i64) @push(i64 %ptrto_{memory}_{c})\n")
                c += 1
            else:
                compiler_error(
                    word.tok,
                    f"Memory {memory} is not defined globally or in proc {proc_name}",
                )
                sys.exit(1)
        elif word.typ == OT.KEYWORD:
            if word.operand == Keyword.PROC:
                assert False, (
                    f"Word: {word} of type keyword:PROC allowed to reach compile_proc_to_ll()"
                )
            if word.operand == Keyword.IF:
                pass
            elif word.operand == Keyword.ELIF:
                out.write(
                    f"  br label %ls{ip}\n"
                )  # So that LLVM thinks the block is 'closed'
                out.write(f"ls{ip}:\n")  # Label to jump to from previous (el)if
                out.write(
                    f"  br label %ls{word.jmp}\n"
                )  # Jump to the end if we hit the elif
                out.write(f"l{ip}:\n")  # Label to jump to from previous (el)if
            elif word.operand == Keyword.WHILE:
                out.write(
                    f"  br label %l{ip}\n"
                )  # So that LLVM thinks the block is 'closed'
                out.write(f"l{ip}:\n")  # Label for the end to jump to
            elif word.operand == Keyword.DO:
                out.write(f"  %a{c} = call i64() @pop()\n")
                # Compare number with 0 (true if a{n} != 0)
                out.write(f"  %b{c} = icmp ne i64 %a{c}, 0\n")
                # Jump to right in front if true, or `end` if false
                out.write(f"  br i1 %b{c}, label %l{ip}, label %l{word.jmp}\n")
                out.write(f"l{ip}:\n")  # Label to jump to if true
                c += 1
            elif word.operand == Keyword.ELSE:
                out.write(f"  br label %l{word.jmp}\n")
                out.write(f"l{ip}:\n")
            elif word.operand == Keyword.END:
                out.write(f"  br label %l{word.jmp}\n")
                out.write(f"l{ip}:\n")
                out.write(f"  br label %ls{ip}\n")  # 'Close' the block for llvm
                out.write(f"ls{ip}:\n")  # Skip label
            else:
                assert False, f"Unknown keyword {word}"
        else:
            assert False, f"Unknown Op Type {word}"

    out.write("  ret void\n")
    out.write("}\n")


def compile_main_function(out: TextIOWrapper):
    """Write LLVM IR for a main function (the entry point) to an open()ed file"""
    out.write("define i64 @main(i64 %argc, ptr %argv) {\n")
    out.write("  %argv_i64 = ptrtoint ptr %argv to i64\n")
    out.write("  call void(i64) @push(i64 %argv_i64)\n")
    out.write("  call void(i64) @push(i64 %argc)\n")
    out.write("  call void() @proc_main()\n")
    out.write("  %returncode = call i64() @pop()\n")
    # TODO: Return the returncode instead
    out.write("  ret i64 0\n")
    out.write("}\n")


def compile_program_to_ll(program: Program, out_file_path: str):
    """Compile a series of Words into an llvm IR file (.ll)"""
    print(f"[INFO] Generating {out_file_path}")
    with open(out_file_path, "w+") as out:
        compile_push_pop_functions(out)
        compile_extern_procs(out, list(program.externs.keys()))
        compile_global_memories(out, program.memories)
        found_main = False
        for proc_name in program.procs:
            if proc_name == "main":
                found_main = True
            compile_proc_to_ll(
                out, proc_name, program.procs[proc_name], program.memories
            )

        if not found_main:
            err_tok = Token(TT.WORD, "", program.file_path, 0, 0)
            compiler_error(err_tok, "No entry point found (expected `proc main ...`)")
            sys.exit(1)
        else:
            compile_main_function(out)


def compile_ll_to_bin(ll_path: str, bin_path: str):
    print(f"[INFO] Compiling `{ll_path}` to native binary")
    this_folder = os.path.split(__file__)[0]
    intrinsics_ll_path = os.path.join(this_folder, "std", "intrinsics.ll")
    files_ll_path = os.path.join(this_folder, "std", "files.ll")
    res = run_echoed(
        [
            "llvm-link",
            ll_path,
            intrinsics_ll_path,
            files_ll_path,
            "-o",
            ll_path,
            "-opaque-pointers",
            "-S",
        ]
    )
    if res.returncode != 0:
        print("error: `llvm-link` finished with non-0 exit code")
        sys.exit(1)
    run_echoed(
        ["llc", ll_path, "-o", bin_path + ".s", "-opaque-pointers"]
    )  # -opaque-pointers argument because newer LLVm versions use [type]* instead of `ptr` type
    res = run_echoed(["clang", bin_path + ".s", "-o", bin_path])
    if res.returncode != 0:
        print("error: `clang` finished with non-0 exit code")
        sys.exit(1)
    print(f"[INFO] Compiled source file to native binary at `{bin_path}`")


def repr_program(program: list[Word]):
    """Generate a pretty-printed string from a program"""
    return "[\n\t" + ",\n\t".join([str(i) for i in program]) + "\n]"


COMMANDS = ["com", "to-ll", "from-ll"]


def usage():
    """Print a message on proper usage of the collver command"""
    print(
        """
USAGE: [python3.10] collver.py <subcommand> <filename> [flags]
    Subcommands:
        com: Compile a source (.collver) file to a binary executable (using clang)
        to-ll: Compile a source (.collver) file to llvm assembly/IR (without calling clang)
        from-ll: Compile an llvm IR (.ll) file to a binary executable (using clang)
    Flags:
        -r: Automatically run executable after compiling (only applicable for `com` command)
    """[1:-5]
    )  # Chop off the initial \n, the final \n, and the 4 spaces at the end


def main():
    if len(sys.argv) < 3:
        usage()
        print("error: Not enough arguments provided", file=sys.stderr)
        sys.exit(1)
    else:
        command = sys.argv[1]
        if command not in COMMANDS:
            usage()
            print(f"error: Unknown subcommand {command}", file=sys.stderr)
            sys.exit(1)
        src_path = sys.argv[2]
        exec_path = os.path.splitext(src_path)[0]
        ll_path = exec_path + ".ll"
    if command != "from-ll":
        try:
            print(f"[INFO] Compiling file {src_path}")
            toks = lex_file(src_path)
            toks = [
                Token(TT.WORD, "include", src_path, 0, 0),
                Token(TT.STRING, "intrinsics.collver", src_path, 0, 0),
            ] + toks
        except FileNotFoundError:
            print(f"error: File `{src_path}` not found!", file=sys.stderr)
            sys.exit(1)

        toks = preprocess_includes(toks, [])
        toks = preprocess_consts(toks)
        toks = preprocess_aliases(toks)
        words = parse_tokens_into_words(toks)
        program: Program = parse_words_into_program(src_path, words)
        for proc in program.procs:
            print(f"{proc}:\n\t{program.procs[proc]}")
        type_check_program(program)
        for proc in program.procs:
            crossreference_proc(program.procs[proc])

        assert False, "We made it this far, poggers"
        compile_program_to_ll(program, ll_path)
    if command in ("com", "from-ll"):
        compile_ll_to_bin(ll_path, exec_path)
        if "/" not in exec_path:
            exec_path = os.path.join(".", exec_path)
        if "-r" in sys.argv:
            print(f"[INFO] Running `{exec_path}`")
            subprocess.run([exec_path])


if __name__ == "__main__":
    main()
