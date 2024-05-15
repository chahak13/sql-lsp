from sqlfluff.core import FluffConfig

fluff_config = FluffConfig(
    {
        "core": {
            "dialect": "mysql",
            "nocolor": True,
            "ignore": "parsing",
            "exclude_rules": ["LT12", "RF02"],
        },
        "indentation": {
            "ignore_comment_lines": True,
        },
    }
)
