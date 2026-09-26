from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path


RESTRICTED_TOKEN_HASHES = frozenset(
    """
00628be195b0bf9a79effae594fd24a3dcc23370b33822a00c819e40bf480459
110e53f01476b1946b6202e98d5e4bcd675efec1db53642819f0d8d60cf1cdb8
12a667c9be6ff8f665d2e9163f3b96422e8025ef238817ec8101c17a23f1a4c3
12c1129b88a8002dcf914033b635c8245cd283b29c12cb2d22278946f17e44ad
16a94b54d7831c789deab25e395553e498eb8ab2e6bea184b9746a46731d399b
2e66065e4b5a707ff8bcd9bc1a97bb2511192cf08c3fb80c1989f984152afcb7
4b17dcf4f097f8bfeb6a3955a73ca7af362cebed87a40d653d505010da7bc673
4c1cd66c13cc9849cd9a24ed1a7636c703ea3c77d7a8e39b9eac85e4dfb74c9e
687b447cee878b1f4e6c655ed606a593229bc7351b43daef7297b798aaa2ba88
6ccffa4977d4246ed9de8ad27693e9802b50d105aae43730d06f1dc840ca6df5
796ee3d0b91c9715472cb5f982ee27c51fedfe5c6dd77502d1d82d423d9436b6
8c5c04391361cbf4afd74c5ed8101ea4af881c4ee3b3df1d5b3716a19b1a834d
93b7654e3f152cf5528f13e63bc64aad723728d30e11d71839de5c612e071a76
9e48f968a599f920b3c753406e8e27fc4c1246af058b7c11d2a02cf187ed7551
a84dee6258e6f990d2d9dff3f662507b787c4b36ab7d8f6843affa6a0374ed13
b5d9c4172f29c5b797383a1012d3cbb843430c0c22f013423c644a55622f5c0d
d46302c0388a04f542f3b353870ac1c2a54595aa03bb2693872c4d82353ef7d5
d516dbecbf6a8cb4d28185bdd60f8faf9c0ceb8e8eabfb987206795e87281310
d5dc6311775ae411f9e2285807870516205266a1d5e4948886d8e446e873cf97
db39009fdacb951e965a64b8e46960134c153a6fb4a38dad59f4b5ec9c05a597
dc738c14b07f2832fd89a258e7efc096bff081c9452b21b79d1f5f687a15eb3d
e50f220c55592c8eb9cb119dfb5d5c2b613e4e95ef06e4d423898f4e6c6862d0
f77e9d6ace861acdd46b83550e5e20977f690fe9dcf5908e07135277442af959
""".split()
)


def _tracked_files(repo_root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    return [repo_root / name.decode("utf-8") for name in result.stdout.split(b"\0") if name]


def test_public_tree_contains_no_restricted_identifiers() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    violations: list[str] = []

    for path in _tracked_files(repo_root):
        relative = path.relative_to(repo_root).as_posix()
        try:
            text = path.read_text(encoding="utf-8").casefold()
        except (UnicodeDecodeError, OSError):
            continue
        for token in re.findall(r"[^\W_]+", text, flags=re.UNICODE):
            candidates = {token}
            candidates.update(
                token[start:end]
                for start in range(len(token))
                for end in range(start + 3, len(token) + 1)
            )
            if any(
                hashlib.sha256(candidate.encode("utf-8")).hexdigest()
                in RESTRICTED_TOKEN_HASHES
                for candidate in candidates
            ):
                violations.append(relative)
                break

    assert not violations, "Restricted identifiers found in: " + ", ".join(sorted(violations))
