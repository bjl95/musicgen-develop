import torchaudio
import torch
from transformers import AutoProcessor, MusicgenForConditionalGeneration, generation
import scipy
from tqdm import tqdm
import os
from argparse import ArgumentParser


def MusicGen_Perplexity(audio_path):
    # load the MusicGen model
    processor = AutoProcessor.from_pretrained("facebook/musicgen-small")
    model = MusicgenForConditionalGeneration.from_pretrained("facebook/musicgen-small")

    # load the music audio file
    default_sample, default_sr = torchaudio.load(audio_path)

    # change the SAMPLING RATE of the audio to be the same as that of the trainded MusicGen model
    new_sr = model.config.audio_encoder.sampling_rate
    sample = torchaudio.functional.resample(default_sample, orig_freq=default_sr, new_freq=new_sr)
    sample = sample[0, :]

    # prepare for the loop of calculating the perplexity (shifted right)
    seq_len = sample.shape[0]
    stride = 2048
    max_length = model.config.max_length

    # start the loop
    ppl_list = []
    prev_end_loc = 0
    for begin_loc in tqdm(range(0, seq_len, stride)):
        end_loc = min(begin_loc + max_length, seq_len)
        trg_len = end_loc - prev_end_loc  # may be different from stride on last loop
        input_sample = sample[begin_loc:end_loc]
        
        # prepare the label of the next token(audio codes), which will be predicted by MisicGen
        tmp_input = processor(
            audio=sample[end_loc:],
            sampling_rate=new_sr,
            padding=True,
            return_tensors="pt",
        )
        tmp_labels = model.get_audio_encoder()(**tmp_input)
        labels = tmp_labels.audio_codes[0,0,:,0]
        labels_onehot = torch.nn.functional.one_hot(labels, num_classes=2048)

        # prepare the input for the MusicGen model
        inputs = processor(
            audio=input_sample,
            sampling_rate=new_sr,
            text = [""],
            padding=True,
            return_tensors="pt",
        )

        with torch.no_grad():
            outputs = model(**inputs)
            logits = outputs.logits[:, 0, :]
            loss_fct = torch.nn.CrossEntropyLoss()

            # calculate the cross entropy (the average of all the losses on each codebook)
            neg_log_likelihood = loss_fct(logits[0], labels_onehot[0].float())
            for i in range(1, logits.shape[0]):
                print(logits[i])
                print(labels_onehot[i])
                neg_log_likelihood += loss_fct(logits[i], labels_onehot[i].float())
            neg_log_likelihood /= logits.shape[0]
            print("NNL:" , neg_log_likelihood)

        # append the value into a list, and continue predicting the next sequence of tokens
        ppl_list.append(neg_log_likelihood)

        prev_end_loc = end_loc
        if end_loc == seq_len:
            break

    # calculate the perplexity
    ppl = torch.exp(torch.stack(ppl_list).mean())
    print("The perplexity of the music audio is: ", ppl)
    

def generate(audio_path, text_prompt=["Energetic EDM"], output_path="./output/musicgen_out.wav"):
    # load the MusicGen model
    processor = AutoProcessor.from_pretrained("facebook/musicgen-small")
    model = MusicgenForConditionalGeneration.from_pretrained("facebook/musicgen-small")

    # load the music audio file
    default_sample, default_sr = torchaudio.load(audio_path)

    # change the SAMPLING RATE of the audio to be the same as that of the trainded MusicGen model
    new_sr = model.config.audio_encoder.sampling_rate
    sample = torchaudio.functional.resample(default_sample, orig_freq=default_sr, new_freq=new_sr)

    # take the first half of the audio sample
    sample = sample[0, : sample.shape[1] // 2]

    # prepare the input for the MusicGen model
    inputs = processor(
        audio=sample,
        sampling_rate=new_sr,
        text=text_prompt,
        padding=True,
        return_tensors="pt",
    )
    
    # continually generate the music audio using the MusicGen model
    expected_token_num = int(sample.shape[0] / new_sr * 46.5)
    audio_values = model.generate(**inputs, do_sample=True, guidance_scale=3, max_new_tokens=expected_token_num)  # noise existing after 30s
    # audio_values = model.generate(**inputs, do_sample=True, guidance_scale=3)   # no noise

    # save the generated audio to a new file
    scipy.io.wavfile.write(output_path, rate=new_sr, data=audio_values[0, 0].numpy())
    


if __name__=="__main__":
    if not os.path.exists("output"):
        os.mkdir("output")

    parser = ArgumentParser()
    parser.add_argument("--method", type=str, required=True, help="The method you want to run.")
    parser.add_argument("--audio", type=str, default='./test.mp3', help="The audio file path.")
    parser.add_argument("--text", type=str, default="Energetic EDM", help="The descrition of the music that you want to generate.")
    parser.add_argument("--output_path", type=str, default="./output/musicgen_out.wav", help="The output wav file path. Notice that wav is an audio format.")

    args = parser.parse_args()
    
    if args.method=="generate":
        generate(args.audio, args.text, args.output_path)
    elif args.method=="evaluate":
        MusicGen_Perplexity(args.audio)
    else:
        print("Method Error: cannot find avaible methods, please check your arguments.")