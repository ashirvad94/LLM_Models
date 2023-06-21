import argparse
from datasets import load_dataset
from huggingface_hub import HfFolder
from random import randrange
from transformers import AutoTokenizer
from itertools import chain
from functools import partial


from itertools import chain
from functools import partial

remainder = {"input_ids": [], "attention_mask": [], "token_type_ids": []}


# empty list to save remainder from batches to use in next batch
def chunk_dataset(dataset, chunk_length=2048):
    def chunk(sample, chunk_length=chunk_length):
        # define global remainder variable to save remainder from batches to use in next batch
        global remainder
        # Concatenate all texts and add remainder from previous batch
        concatenated_examples = {k: list(chain(*sample[k])) for k in sample.keys()}
        concatenated_examples = {k: remainder[k] + concatenated_examples[k] for k in concatenated_examples.keys()}
        # get total number of tokens for batch
        batch_total_length = len(concatenated_examples[list(sample.keys())[0]])

        # get max number of chunks for batch
        if batch_total_length >= chunk_length:
            batch_chunk_length = (batch_total_length // chunk_length) * chunk_length

        # Split by chunks of max_len.
        result = {
            k: [t[i : i + chunk_length] for i in range(0, batch_chunk_length, chunk_length)]
            for k, t in concatenated_examples.items()
        }
        # add remainder to global variable for next batch
        remainder = {k: concatenated_examples[k][batch_chunk_length:] for k in concatenated_examples.keys()}
        # prepare labels
        result["labels"] = result["input_ids"].copy()
        return result

    # tokenize and chunk dataset
    lm_dataset = dataset.map(
        partial(chunk, chunk_length=2048),
        batched=True,
    )
    print(f"Total number of samples: {len(lm_dataset)}")
    return lm_dataset


def parse_args():
    """Parse the arguments."""
    parser = argparse.ArgumentParser()
    # add model id and dataset path argument
    parser.add_argument("--model_id", type=str, default="google/flan-t5-xl", help="Model id to use for training.")
    parser.add_argument("--save_path", type=str, default="data", help="Path to save the processed dataset.")
    parser.add_argument("--trust_remote_code", type=bool, default=False, help="Path to save the processed dataset.")
    parser.add_argument("--model_max_length", type=int, default=2048, help="Path to save the processed dataset.")
    parser.add_argument(
        "--hf_token",
        type=str,
        default=HfFolder.get_token(),
        help="Token to use for uploading models to Hugging Face Hub.",
    )
    args = parser.parse_known_args()
    return args


def format_dolly(sample):
    instruction = f"### Instruction\n{sample['instruction']}"
    context = f"### Context\n{sample['context']}" if len(sample["context"]) > 0 else None
    response = f"### Answer\n{sample['response']}"
    # join all the parts together
    prompt = "\n\n".join([i for i in [instruction, context, response] if i is not None])
    return prompt


def create_dataset(args):
    # Load dataset from the hub
    dataset = load_dataset("databricks/databricks-dolly-15k", split="train")

    print(f"dataset size: {len(dataset)}")
    print(dataset[randrange(len(dataset))])
    print(format_dolly(dataset[randrange(len(dataset))]))

    tokenizer = AutoTokenizer.from_pretrained(args.model_id, trust_remote_code=args.trust_remote_code)
    tokenizer.pad_token = tokenizer.eos_token

    # template dataset to add prompt to each sample
    def template_dataset(sample):
        sample["text"] = f"{format_dolly(sample)}{tokenizer.eos_token}"
        return sample

    # apply prompt template per sample
    dataset = dataset.map(template_dataset, remove_columns=list(dataset.features))
    # tokenize dataset
    dataset = dataset.map(
        lambda sample: tokenizer(sample["text"]), batched=True, remove_columns=list(dataset.features)
    )

    # chunk dataset
    lm_dataset = chunk_dataset(dataset, chunk_length=args.model_max_length)

    # save dataset
    lm_dataset.save_to_disk(args.save_path)


def main():
    args, _ = parse_args()
    create_dataset(args)


if __name__ == "__main__":
    main()

# python training/preprocessing/create_dolly_dataset.py \
#   --model_id tiiuae/falcon-7b \
#   --trust_remote_code True
