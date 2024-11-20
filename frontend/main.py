"""A little helper module for running streamlit using a poetry command."""

import sys

from streamlit.web import cli as stcli


def main():
    """Run the streamlit app."""
    sys.argv = ["streamlit", "run", "frontend/app.py"]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
