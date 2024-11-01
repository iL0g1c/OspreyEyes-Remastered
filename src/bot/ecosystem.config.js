module.exports = {
    apps: [
      {
        name: "OspreyEyes",
        script: "MindsEye.py", // Replace with your bot's main script
        interpreter: "python3",
        env: {
          PYTHONPATH: "../../venv/bin/python"
        },
      },
    ],
  };
  