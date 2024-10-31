module.exports = {
    apps: [
      {
        name: "OspreyEyesBackground",
        script: "dataCollectionLayer.py", // Replace with your bot's main script
        interpreter: "python3",
        env: {
          PYTHONPATH: "../../venv/bin/python"
        },
      },
    ],
  };
  