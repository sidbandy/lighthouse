"""Reference data: patterns, problems, topics, and where to actually learn them.

Kept as config rather than a table, like the selectivity tiers and the
competency list. It is legible in a diff, versioned with the code, and needs no
migration to correct -- and correcting it is the normal case, because what gets
asked changes.

Three vocabularies, and they answer different questions:

* **Patterns** are what interviews test. Individual problems get retired;
  "sliding window" does not. Everything aggregates to patterns.
* **Problems** are the concrete practice. The core set is small on purpose --
  a list of four hundred is a list nobody starts.
* **Topics** are everything that is not an algorithm question: system design,
  security, a specific language. Each carries ``triggers`` -- the terms that,
  when they show up in the jobs the operator actually applied to, mean this
  topic is worth their time. That link is the whole point: the answer to "what
  should I study" should come from where they applied, not from a generic list.

Every resource here is real, free unless marked, and checked. A study plan that
sends someone to a dead link is worse than one that says nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Resource:
    """Somewhere to actually learn the thing."""

    label: str
    url: str
    kind: str  # practice | reading | reference | course
    note: str = ""
    is_free: bool = True


@dataclass(frozen=True, slots=True)
class Pattern:
    """One algorithmic idea, and the ones it assumes you already have."""

    slug: str
    name: str
    blurb: str
    prerequisites: tuple[str, ...] = ()
    resources: tuple[Resource, ...] = ()


@dataclass(frozen=True, slots=True)
class Problem:
    slug: str
    title: str
    difficulty: str  # easy | medium | hard
    patterns: tuple[str, ...]
    # The set worth doing before anything else. Deliberately small.
    is_core: bool = False

    @property
    def url(self) -> str:
        return f"https://leetcode.com/problems/{self.slug}/"


@dataclass(frozen=True, slots=True)
class Topic:
    """Something to study that is not an algorithm question."""

    slug: str
    name: str
    blurb: str
    # Terms in a job description that mean this topic is worth the time. Matched
    # against what the operator's own applications ask for.
    triggers: tuple[str, ...]
    resources: tuple[Resource, ...] = field(default_factory=tuple)
    # Rough hours to a working level. A range, because it is a range.
    hours_low: int = 6
    hours_high: int = 20


_NEETCODE = "https://neetcode.io/practice"
_PRIMER = "https://github.com/donnemartin/system-design-primer"

PATTERNS: tuple[Pattern, ...] = (
    Pattern(
        "arrays_hashing",
        "Arrays and hashing",
        "Counting, lookups, and the trick of trading memory for a scan.",
        resources=(
            Resource("NeetCode — Arrays & Hashing", _NEETCODE, "practice"),
        ),
    ),
    Pattern(
        "two_pointers",
        "Two pointers",
        "Walking a sorted structure from both ends, or at two speeds.",
        prerequisites=("arrays_hashing",),
        resources=(Resource("NeetCode — Two Pointers", _NEETCODE, "practice"),),
    ),
    Pattern(
        "sliding_window",
        "Sliding window",
        "A contiguous range you grow and shrink instead of re-scanning.",
        prerequisites=("two_pointers",),
        resources=(Resource("NeetCode — Sliding Window", _NEETCODE, "practice"),),
    ),
    Pattern(
        "binary_search",
        "Binary search",
        "Halving a space — including spaces that are not obviously sorted.",
        prerequisites=("arrays_hashing",),
        resources=(Resource("NeetCode — Binary Search", _NEETCODE, "practice"),),
    ),
    Pattern(
        "stack",
        "Stacks and monotonic stacks",
        "Matching, nesting, and 'the next greater thing'.",
        prerequisites=("arrays_hashing",),
        resources=(Resource("NeetCode — Stack", _NEETCODE, "practice"),),
    ),
    Pattern(
        "linked_list",
        "Linked lists",
        "Pointer surgery. Mechanical once you have done a few.",
        prerequisites=("two_pointers",),
        resources=(Resource("NeetCode — Linked List", _NEETCODE, "practice"),),
    ),
    Pattern(
        "trees",
        "Trees",
        "Recursion with a shape. Traversals, depth, and building from them.",
        prerequisites=("linked_list",),
        resources=(Resource("NeetCode — Trees", _NEETCODE, "practice"),),
    ),
    Pattern(
        "graphs",
        "Graphs",
        "BFS, DFS, and recognising a grid or a dependency list as a graph.",
        prerequisites=("trees",),
        resources=(
            Resource("NeetCode — Graphs", _NEETCODE, "practice"),
            Resource(
                "CP-Algorithms — graph traversal",
                "https://cp-algorithms.com/graph/breadth-first-search.html",
                "reading",
                "Denser than most tutorials; worth it once BFS clicks.",
            ),
        ),
    ),
    Pattern(
        "heap",
        "Heaps and priority queues",
        "Top-k, streaming medians, and scheduling.",
        prerequisites=("trees",),
        resources=(Resource("NeetCode — Heap / Priority Queue", _NEETCODE, "practice"),),
    ),
    Pattern(
        "backtracking",
        "Backtracking",
        "Enumerating choices and undoing them. Subsets, permutations, n-queens.",
        prerequisites=("trees",),
        resources=(Resource("NeetCode — Backtracking", _NEETCODE, "practice"),),
    ),
    Pattern(
        "dynamic_programming",
        "Dynamic programming",
        "Recognising overlapping subproblems, then writing the recurrence down.",
        prerequisites=("backtracking",),
        resources=(
            Resource("NeetCode — 1-D and 2-D DP", _NEETCODE, "practice"),
            Resource(
                "Errichto — DP lecture",
                "https://www.youtube.com/watch?v=YBSt1jYwVfU",
                "course",
                "The clearest free explanation of building a recurrence.",
            ),
        ),
    ),
    Pattern(
        "intervals",
        "Intervals",
        "Sorting by an endpoint and sweeping. Merging, overlaps, meeting rooms.",
        prerequisites=("arrays_hashing",),
        resources=(Resource("NeetCode — Intervals", _NEETCODE, "practice"),),
    ),
    Pattern(
        "greedy",
        "Greedy",
        "Taking the locally best step, and the argument that it is safe.",
        prerequisites=("arrays_hashing",),
        resources=(Resource("NeetCode — Greedy", _NEETCODE, "practice"),),
    ),
    Pattern(
        "math_bits",
        "Math and bit manipulation",
        "Modular arithmetic, primes, and the handful of bit tricks that recur.",
        resources=(Resource("NeetCode — Bit Manipulation", _NEETCODE, "practice"),),
    ),
)

PATTERNS_BY_SLUG: dict[str, Pattern] = {p.slug: p for p in PATTERNS}


# A small core set. Each is widely used as the canonical example of its pattern,
# which is what makes it worth the hour -- you are learning the shape, not
# collecting a number.
PROBLEMS: tuple[Problem, ...] = (
    Problem("two-sum", "Two Sum", "easy", ("arrays_hashing",), is_core=True),
    Problem("contains-duplicate", "Contains Duplicate", "easy", ("arrays_hashing",), is_core=True),
    Problem("valid-anagram", "Valid Anagram", "easy", ("arrays_hashing",)),
    Problem("group-anagrams", "Group Anagrams", "medium", ("arrays_hashing",), is_core=True),
    Problem(
        "product-of-array-except-self",
        "Product of Array Except Self",
        "medium",
        ("arrays_hashing",),
        is_core=True,
    ),
    Problem("valid-palindrome", "Valid Palindrome", "easy", ("two_pointers",), is_core=True),
    Problem("3sum", "3Sum", "medium", ("two_pointers",), is_core=True),
    Problem(
        "container-with-most-water", "Container With Most Water", "medium", ("two_pointers",)
    ),
    Problem(
        "best-time-to-buy-and-sell-stock",
        "Best Time to Buy and Sell Stock",
        "easy",
        ("sliding_window",),
        is_core=True,
    ),
    Problem(
        "longest-substring-without-repeating-characters",
        "Longest Substring Without Repeating Characters",
        "medium",
        ("sliding_window",),
        is_core=True,
    ),
    Problem(
        "minimum-window-substring", "Minimum Window Substring", "hard", ("sliding_window",)
    ),
    Problem("binary-search", "Binary Search", "easy", ("binary_search",), is_core=True),
    Problem(
        "search-in-rotated-sorted-array",
        "Search in Rotated Sorted Array",
        "medium",
        ("binary_search",),
        is_core=True,
    ),
    Problem("koko-eating-bananas", "Koko Eating Bananas", "medium", ("binary_search",)),
    Problem("valid-parentheses", "Valid Parentheses", "easy", ("stack",), is_core=True),
    Problem("daily-temperatures", "Daily Temperatures", "medium", ("stack",), is_core=True),
    Problem("reverse-linked-list", "Reverse Linked List", "easy", ("linked_list",), is_core=True),
    Problem("merge-two-sorted-lists", "Merge Two Sorted Lists", "easy", ("linked_list",)),
    Problem("linked-list-cycle", "Linked List Cycle", "easy", ("linked_list", "two_pointers")),
    Problem(
        "lru-cache", "LRU Cache", "medium", ("linked_list", "arrays_hashing"), is_core=True
    ),
    Problem(
        "invert-binary-tree", "Invert Binary Tree", "easy", ("trees",), is_core=True
    ),
    Problem(
        "maximum-depth-of-binary-tree", "Maximum Depth of Binary Tree", "easy", ("trees",)
    ),
    Problem(
        "binary-tree-level-order-traversal",
        "Binary Tree Level Order Traversal",
        "medium",
        ("trees", "graphs"),
        is_core=True,
    ),
    Problem(
        "validate-binary-search-tree", "Validate Binary Search Tree", "medium", ("trees",),
        is_core=True,
    ),
    Problem("number-of-islands", "Number of Islands", "medium", ("graphs",), is_core=True),
    Problem("clone-graph", "Clone Graph", "medium", ("graphs",)),
    Problem("course-schedule", "Course Schedule", "medium", ("graphs",), is_core=True),
    Problem(
        "pacific-atlantic-water-flow", "Pacific Atlantic Water Flow", "medium", ("graphs",)
    ),
    Problem("kth-largest-element-in-an-array", "Kth Largest Element", "medium", ("heap",),
            is_core=True),
    Problem("top-k-frequent-elements", "Top K Frequent Elements", "medium",
            ("heap", "arrays_hashing"), is_core=True),
    Problem("find-median-from-data-stream", "Find Median from Data Stream", "hard", ("heap",)),
    Problem("subsets", "Subsets", "medium", ("backtracking",), is_core=True),
    Problem("combination-sum", "Combination Sum", "medium", ("backtracking",)),
    Problem("word-search", "Word Search", "medium", ("backtracking", "graphs")),
    Problem("climbing-stairs", "Climbing Stairs", "easy", ("dynamic_programming",),
            is_core=True),
    Problem("house-robber", "House Robber", "medium", ("dynamic_programming",), is_core=True),
    Problem("coin-change", "Coin Change", "medium", ("dynamic_programming",), is_core=True),
    Problem(
        "longest-common-subsequence",
        "Longest Common Subsequence",
        "medium",
        ("dynamic_programming",),
    ),
    Problem("merge-intervals", "Merge Intervals", "medium", ("intervals",), is_core=True),
    Problem("insert-interval", "Insert Interval", "medium", ("intervals",)),
    Problem("non-overlapping-intervals", "Non-overlapping Intervals", "medium",
            ("intervals", "greedy")),
    Problem("jump-game", "Jump Game", "medium", ("greedy",), is_core=True),
    Problem("gas-station", "Gas Station", "medium", ("greedy",)),
    Problem("number-of-1-bits", "Number of 1 Bits", "easy", ("math_bits",)),
    Problem("missing-number", "Missing Number", "easy", ("math_bits", "arrays_hashing")),
)

PROBLEMS_BY_SLUG: dict[str, Problem] = {p.slug: p for p in PROBLEMS}


# Everything that is not an algorithm question. `triggers` are matched against
# what the operator's own applications actually ask for, which is what makes
# this a recommendation rather than a syllabus.
TOPICS: tuple[Topic, ...] = (
    Topic(
        "system_design",
        "System design",
        "Load balancing, caching, sharding, queues, and the tradeoffs between "
        "them. Uncommon in intern loops and normal for new-grad ones.",
        triggers=(
            "distributed systems", "scalability", "microservices", "system design",
            "high availability", "load balanc", "horizontally scal",
        ),
        resources=(
            Resource("System Design Primer", _PRIMER, "reading",
                     "The standard free starting point. Read it, don't skim it."),
            Resource("ByteByteGo — system design basics",
                     "https://bytebytego.com/", "course",
                     "Clearer diagrams than the primer.", is_free=False),
        ),
        hours_low=12,
        hours_high=40,
    ),
    Topic(
        "security",
        "Security fundamentals",
        "Injection, auth, secrets handling, and the top-ten list every reviewer "
        "checks against.",
        triggers=(
            "security", "cybersecurity", "vulnerability", "penetration", "owasp",
            "cryptography", "authentication", "authorization", "appsec",
        ),
        resources=(
            Resource("OWASP Top Ten", "https://owasp.org/www-project-top-ten/", "reference",
                     "Know all ten and one concrete example of each."),
            Resource("PortSwigger Web Security Academy",
                     "https://portswigger.net/web-security", "practice",
                     "Free, hands-on labs. The best free resource here by some way."),
        ),
        hours_low=8,
        hours_high=30,
    ),
    Topic(
        "sql",
        "SQL",
        "Joins, aggregation, window functions. Asked directly in data and "
        "analytics loops, and assumed everywhere else.",
        triggers=("sql", "postgresql", "mysql", "etl", "data warehouse", "data pipeline"),
        resources=(
            Resource("Mode SQL Tutorial", "https://mode.com/sql-tutorial/", "course"),
            Resource("LeetCode — Database", "https://leetcode.com/problemset/database/",
                     "practice", "Closest to how SQL is actually tested."),
        ),
    ),
    Topic(
        "concurrency",
        "Concurrency",
        "Threads, locks, races, and async. Asked more often than people expect "
        "in systems and backend loops.",
        triggers=("concurrency", "multithreading", "multi-threaded", "goroutines", "thread-safe"),
        resources=(
            Resource("Go by Example — goroutines",
                     "https://gobyexample.com/goroutines", "reading"),
            Resource("Python asyncio docs",
                     "https://docs.python.org/3/library/asyncio.html", "reference"),
        ),
    ),
    Topic(
        "ml_fundamentals",
        "ML fundamentals",
        "Bias/variance, evaluation metrics, overfitting, and being able to "
        "explain a model you actually built.",
        triggers=(
            "machine learning", "deep learning", "pytorch", "tensorflow", "nlp",
            "neural network", "model training", "llm", "computer vision",
        ),
        resources=(
            Resource("Google ML Crash Course",
                     "https://developers.google.com/machine-learning/crash-course", "course"),
            Resource("StatQuest", "https://www.youtube.com/@statquest", "course",
                     "For the statistics half, which is where interviews probe."),
        ),
        hours_low=10,
        hours_high=40,
    ),
    Topic(
        "probability",
        "Probability and mental maths",
        "Expected value, conditional probability, and estimating out loud under "
        "time pressure. The core of a quant screen.",
        triggers=("probability", "stochastic", "expected value", "quantitative research",
                  "quantitative trading", "derivatives pricing"),
        resources=(
            Resource("Green Book (Xinfeng Zhou) — quant interview questions",
                     "https://www.goodreads.com/book/show/3574541", "reading",
                     "The standard. Work the problems, don't read the answers.",
                     is_free=False),
            Resource("Brilliant — probability", "https://brilliant.org/courses/probability/",
                     "course", is_free=False),
        ),
        hours_low=15,
        hours_high=50,
    ),
    Topic(
        "cloud",
        "Cloud and deployment",
        "What a container is, what an orchestrator does, and how your code gets "
        "from a laptop to production.",
        triggers=("aws", "gcp", "azure", "kubernetes", "docker", "terraform", "ci/cd",
                  "devops", "infrastructure"),
        resources=(
            Resource("Docker — getting started",
                     "https://docs.docker.com/get-started/", "course"),
            Resource("roadmap.sh — DevOps", "https://roadmap.sh/devops", "reference",
                     "Use it to find gaps, not as a checklist to complete."),
        ),
    ),
    Topic(
        "operating_systems",
        "Operating systems and networking",
        "Processes vs threads, memory, TCP, HTTP. Assumed knowledge that gets "
        "checked directly in systems loops.",
        triggers=("operating system", "kernel", "tcp/ip", "systems programming",
                  "embedded systems", "device driver"),
        resources=(
            Resource("OSTEP (free textbook)", "https://pages.cs.wisc.edu/~remzi/OSTEP/",
                     "reading", "Genuinely readable for a textbook."),
            Resource("High Performance Browser Networking",
                     "https://hpbn.co/", "reading"),
        ),
        hours_low=10,
        hours_high=40,
    ),
    Topic(
        "financial_modeling",
        "Financial modelling and accounting",
        "Three-statement modelling, valuation, and reading a filing. Tested "
        "directly in banking and finance loops.",
        triggers=("financial modeling", "valuation", "accounting", "dcf", "equity research",
                  "investment banking", "gaap", "financial analysis"),
        resources=(
            Resource("Wall Street Prep — free crash courses",
                     "https://www.wallstreetprep.com/knowledge/", "reading"),
            Resource("Aswath Damodaran — valuation lectures",
                     "https://pages.stern.nyu.edu/~adamodar/", "course",
                     "Free, and the reference everyone else is summarising."),
        ),
        hours_low=15,
        hours_high=50,
    ),
    Topic(
        "case_interview",
        "Case interviews",
        "Structuring an ambiguous business problem out loud. The whole "
        "consulting loop.",
        triggers=("case interview", "management consulting", "market sizing",
                  "business case"),
        resources=(
            Resource("Case Interview Prep — PrepLounge drills",
                     "https://www.preplounge.com/en/case-interview-basics", "practice"),
            Resource("Victor Cheng — Look Over My Shoulder", "https://www.caseinterview.com/",
                     "course", is_free=False),
        ),
        hours_low=15,
        hours_high=40,
    ),
    Topic(
        "product_sense",
        "Product sense and metrics",
        "Picking a metric, arguing a tradeoff, and designing an experiment.",
        triggers=("product management", "product sense", "a/b test", "user research",
                  "product roadmap"),
        resources=(
            Resource("Lenny's Newsletter — PM interview archive",
                     "https://www.lennysnewsletter.com/", "reading"),
            Resource("Stratechery archives", "https://stratechery.com/", "reading",
                     "For the strategy half."),
        ),
    ),
)

TOPICS_BY_SLUG: dict[str, Topic] = {t.slug: t for t in TOPICS}


def core_problems() -> list[Problem]:
    """The set worth doing before anything else."""
    return [p for p in PROBLEMS if p.is_core]


def problems_for(pattern_slug: str) -> list[Problem]:
    """Every catalogued problem for one pattern, easiest first."""
    order = {"easy": 0, "medium": 1, "hard": 2}
    return sorted(
        (p for p in PROBLEMS if pattern_slug in p.patterns),
        key=lambda p: (order.get(p.difficulty, 3), not p.is_core, p.title),
    )
