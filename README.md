# Rubitherm Capstone

## Project Description
Rubitherm Capstone is a machine learning project designed to classify emails into two categories: **offer** or **request**. The project leverages natural language processing and custom ML models to extract relevant information and predict the intention behind incoming emails, facilitating automated email handling.

---

## Directory Structure

- **data/**  
  Contains the raw and processed email datasets. This directory should include annotated emails with labels indicating whether they are offers or requests.

- **models/**  
  Stores trained machine learning models and associated artifacts. Models saved here can be loaded for inference or further training.

- **notebooks/**  
  Jupyter notebooks for exploratory data analysis, model development, training, and evaluation.

- **src/**  
  The main source code for the project, organized into subdirectories:
  - **pipeline/**  
    Contains the modular pipeline components such as `ai_extract_person`, `ai_extract_company`, `ai_predict_intention`, and `ai_controller` that process emails and perform predictions.
  - **tests/**  
    Unit and integration tests for the codebase. Includes `.eml` test email files and optional `.expected.json` files for assertion testing.
  - **utils/**  
    Utility scripts and helper functions used throughout the project.

---

## Setup Instructions

### Prerequisites
- Python 3.8 or higher
- `pyenv` for Python version management (optional but recommended)
- `make` utility (optional for convenience)

### Environment Setup

#### Using pyenv and Makefile (Linux/Mac)
1. Install `pyenv` if not already installed.
2. Run `make setup` to create a virtual environment and install dependencies.
3. Activate the environment with `pyenv activate rubitherm-capstone` or follow instructions printed by the Makefile.

#### Manual Setup (Linux/Mac)
1. Install Python 3.8+.
2. Create a virtual environment:
   ```
   python3 -m venv venv
   source venv/bin/activate
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

#### Manual Setup (Windows)
1. Install Python 3.8+.
2. Create and activate a virtual environment:
   ```
   python -m venv venv
   venv\Scripts\activate
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

---

## Data

The project expects an email dataset consisting of `.eml` files annotated with labels indicating whether each email is an offer or a request. These files should be placed in the `data/` directory. Proper annotation is crucial for supervised model training and evaluation.

---

## Model Development

Model training and experimentation are conducted within the `notebooks/` directory. Use these notebooks to preprocess data, train models, and evaluate performance. Once trained, save the models and related artifacts to the `models/` directory for deployment and inference.

---

## Pipeline Components

The project pipeline consists of several modular components located in `src/pipeline/`:

- **ai_extract_person**: Extracts personal information from emails.
- **ai_extract_company**: Extracts company-related information.
- **ai_predict_intention**: Predicts whether an email is an offer or a request using trained ML models.
- **ai_controller**: Orchestrates the execution of the pipeline components in sequence.

The pipeline can be executed from the command line via the entry point:

```
python -m src.main
```

---

## Testing

Test emails in `.eml` format are located in `src/tests/emails/`. Each test email may have an optional `.expected.json` file containing expected outputs for assertions.

Tests are implemented using Python's `unittest` framework and can also be run with `pytest` for convenience.

To run tests:

```
python -m unittest discover src/tests
```

or

```
pytest src/tests
```

---

## Usage Example

1. Add new `.eml` email files to the `data/` directory.
2. Run the pipeline to process and classify emails:

   ```
   python -m src.main
   ```

3. To retrain models with updated data, use the notebooks in `notebooks/` and save the resulting models to `models/`.

---

## Limitations & Next Steps

- Current models may have limited accuracy depending on dataset size and quality.
- Pipeline components are modular but may require fine-tuning for edge cases.
- Future work includes expanding dataset, improving NLP components, and integrating with email servers for real-time processing.

---

## License

This project is licensed under the [Insert License Name Here].
