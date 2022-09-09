from dataclasses import dataclass
import os
import glob
import subprocess

@dataclass
class TestSpec:
    """A collver Test Specification, containing input and expected outputs"""
    file_path: str # Path to the test spec file
    compiler_stderr: bytes
    provided_input: str
    expected_stdout: bytes
    expected_stderr: bytes

@dataclass
class TestResult:
    """The result of a collver test, with the actual values"""
    test_spec: TestSpec
    compiler_stderr: bytes
    compile_success: bool
    actual_stdout: bytes
    actual_stderr: bytes


def eat_chunk(rlines: list[str]) -> str:
    """Eat a chunk of lines until the next [!MARKER]"""
    out = ""
    if len(rlines):
        line = rlines.pop()
    else:
        return out

    while len(rlines) and not line.startswith("[!"):
        out += line
        line = rlines.pop()

    if line.startswith("[!"):
        rlines.append(line)
    else:
        out += line

    return out

def parse_spec(spec_path: str) -> TestSpec:
    """Parse a test spec file into a text spec object"""
    spec = TestSpec("", b"", "", b"", b"")
    with open(spec_path, "r") as f:
        lines = f.readlines()

    rlines = list(reversed(lines))
    while len(rlines):
        line = rlines.pop()
        if line == "[!FILE]\n":
            spec_folder = os.path.split(spec_path)[0]
            file_line = rlines.pop().strip()
            file_path = os.path.join(spec_folder, file_line)
            spec.file_path = file_path
        elif line == "[!COMERR]\n":
            spec.compiler_stderr = eat_chunk(rlines).encode("utf-8")
        elif line == "[!STDIN]\n":
            spec.provided_input = eat_chunk(rlines)
        elif line == "[!STDOUT]\n":
            spec.expected_stdout = eat_chunk(rlines).encode("utf-8")
        elif line == "[!STDERR]\n":
            spec.expected_stderr = eat_chunk(rlines).encode("utf-8")

    return spec

def run_echoed(cmd: list[str], print_outs: bool=False):
    print(f"[test.py] {'' if print_outs else '[silenced] ' }$ {' '.join(cmd)}")
    run_res = subprocess.run(cmd, capture_output=True)
    if print_outs:
        print("=> STDOUT:\n"+ run_res.stdout.decode("utf-8") + "\n<<")
        print("=> STDERR:\n"+ run_res.stderr.decode("utf-8") + "\n<<")

    return run_res

def run_spec(spec: TestSpec) -> TestResult:
    com_res = run_echoed(["python3.10", "collver.py", "to-ll", spec.file_path])
    if com_res.returncode != 0:
        return TestResult(spec, com_res.stderr, False, b"", b"")
    ll_path = os.path.splitext(spec.file_path)[0] + ".ll"
    run_echoed(["python3.10", "collver.py", "from-ll", ll_path])
    bin_path = os.path.splitext(spec.file_path)[0]
    run_res = run_echoed([bin_path])
    return TestResult(spec, com_res.stderr, True, run_res.stdout, run_res.stderr)

@dataclass
class Problem:
    """A problem (failed test)"""
    field: str    # Name of what didn't match
    expected: str # What was expected
    actual: str   # The actual value

def print_problem(prob: Problem):
    print(f"[test.py] FAILURE: {prob.field} didn't match!")
    print("=> Expected:\n"+ prob.expected)
    print("=> Actual:\n"+ prob.actual)


def check_match(fn: str, fieldname: str, expected: str, actual: str) -> list[Problem]:
    if expected != actual:
        return [
            Problem(
                f"`{fieldname}` for file `{fn}`",
                expected,
                actual,
            )
        ]

    return []


def test_output(res: TestResult) -> list[Problem]:
    probs: list[Problem] = []
    basename = os.path.basename(res.test_spec.file_path)
    # -- Compiler stderr --
    probs.extend(
        check_match(
            basename,
            "Compiler stderr",
            res.test_spec.compiler_stderr.decode("utf-8"),
            res.compiler_stderr.decode("utf-8"),
        )
    )

    if not res.compile_success:
        return probs # Don't bother to check the binary run results if the compile failed

    probs.extend(
        check_match(
            basename,
            "File stdout",
            res.test_spec.expected_stdout.decode("utf-8"),
            res.actual_stdout.decode("utf-8"),
        )
    )

    probs.extend(
        check_match(
            basename,
            "File stderr",
            res.test_spec.expected_stderr.decode("utf-8"),
            res.actual_stderr.decode("utf-8"),
        )
    )

    return probs

def test_specfile(fp: str) -> list[Problem]:
    spec = parse_spec(fp)
    res = run_spec(spec)
    probs = test_output(res)
    return probs

def find_specfiles() -> list[str]:
    """Find specfiles in the ./tests/ folder"""
    return [str(g) for g in glob.glob("./tests/*.cts")]

def main():
    specs = find_specfiles()
    probs = []
    for spec in specs:
        probs.extend(test_specfile(spec))

    if len(probs) == 0:
        print(f"==> Success! {len(specs)} spec(s) tested; 0 failed")
    else:
        print(f"==>Failure: Of {len(specs)} spec(s), {len(probs)} test(s) failed:")
        for prob in probs:
            print_problem(prob)

if __name__ == '__main__':
    main()
