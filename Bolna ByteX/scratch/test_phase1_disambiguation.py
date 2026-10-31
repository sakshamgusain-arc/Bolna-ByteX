import re

CODE_LANG_PATTERN = r"(?:python|py|c\+\+|cpp|c|java|javascript|typescript|js|ts|rust|go|golang|c#|csharp|html|css|sql|bash|sh|ruby|php|kotlin|swift)"
CODE_NOUN_PATTERN = r"(?:program|script|solution|function|code|app|algorithm|class|method)"

def check_code_gen(clause: str) -> bool:
    if re.match(r"^print\s+(?:all\s+)?(?:prime\s+numbers|primes|fibonacci|even\s+numbers|odd\s+numbers)\b", clause, flags=re.IGNORECASE):
        return True
    elif re.match(r"^(?:code|implement)\s+(?:a\s+|an\s+)?(?:solution|algorithm|function|code|program)?\s*(?:to|for|that|which)?\s*(.+)$", clause, flags=re.IGNORECASE):
        return True
    elif re.match(rf"^(?:write|create|generate|build)\s+(?:a\s+|an\s+)?(?:{CODE_LANG_PATTERN}\s+)?{CODE_NOUN_PATTERN}\b", clause, flags=re.IGNORECASE):
        return True
    elif re.match(rf"^(?:write|create|generate|build|code)\s+(?:code\s+)?in\s+{CODE_LANG_PATTERN}\b", clause, flags=re.IGNORECASE):
        return True
    elif re.search(rf"\b(?:in|using|with)\s+{CODE_LANG_PATTERN}\b", clause, flags=re.IGNORECASE) and any(w in clause.lower() for w in ["write", "code", "create", "implement", "generate", "build", "reverse", "sort", "algorithm", "fibonacci", "primes", "factorial"]):
        return True
    return False

test_cases = [
    ("write I am Yash", False),
    ("write I am Yash in Notepad", False),
    ("type hello world", False),
    ("enter my credentials", False),
    ("Write a Python program that prints Hello World", True),
    ("Write code in C++ to reverse an array", True),
    ("create a script to download images", True),
    ("implement binary search", True),
    ("code merge sort in Python", True),
    ("write a function to add two numbers", True),
    ("print all prime numbers up to 100", True)
]

for text, expected in test_cases:
    actual = check_code_gen(text)
    assert actual == expected, f"FAILED for '{text}': expected {expected}, got {actual}"
    print(f"PASS: '{text}' -> code_gen={actual}")

print("\nAll 11 disambiguation assertions passed!")

