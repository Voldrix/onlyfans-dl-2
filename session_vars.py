import os

## Copy everything between the 'snip here' comments to "session_vars_local.py" and fill in the values as per the readme ##
## <----------- >8 snip here
## These Session Variables may need to be updated every time you re-login to OF, or when your browser updates

USER_ID = ""
USER_AGENT = ""
SESS_COOKIE = ""
X_BC = ""

# any profile names to ignore can be put in this array
IGNORELIST = [  ]

# What ruleset do we use?
RULESURL = ""

## <----------- >8 snip here
## Don't include anything eblow this line

lvars="session_vars_local.py"
# If the local variables file exists, load its content and override variables
current_dir = os.path.dirname(os.path.abspath(__file__))
overrides = os.path.join(current_dir, lvars)

if os.path.exists(overrides):
    # Import local variables dynamically
    import importlib.util

    spec = importlib.util.spec_from_file_location(lvars.replace(".py", ""), overrides)
    local_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(local_module)

    # Override the variables in the current module's namespace
    globals().update({k: v for k, v in vars(local_module).items()})
