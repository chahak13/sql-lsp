from sqlfluff.core import FluffConfig

fluff_config = FluffConfig(
    {
        "core": {
            "dialect": "mysql",
            "nocolor": True,
            "ignore": "parsing",
            "exclude_rules": ["LT12"],
        },
        "indentation": {
            "ignore_comment_lines": True,
        },
    }
)
