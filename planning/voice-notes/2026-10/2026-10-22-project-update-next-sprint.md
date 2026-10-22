# 2026-10-22: project update and next sprint (what Hebrish is, the models, the app sprint)

- Audio: [2026-10-22-project-update-next-sprint.opus](2026-10-22-project-update-next-sprint.opus)
  (67:03, Opus 24 kbps, from the lightly cleaned recording; the same audio as MP3 with a waveform
  player and an edited transcript: <https://hebrish.app/updates>)
- Recorded: 2026-10-22 14:03 on a phone sound recorder (67:27 as recorded)
- Processed: 2026-10-22, requests R-2026-10-22-23 to -35; decisions D-2026-10-22-15, -16, -17.
  The project-level context drawn from it (what Hebrish is, model lines and data, product
  principles, tasks outside the apps) is on hebrish.app: <https://hebrish.app/project-context/README.md>
- Transcribed by AssemblyAI on the cleaned audio, so timestamps match the file above. Only misheard
  words and names were fixed (table at the end); square brackets are editorial notes. The name of
  a personal model that is not part of Hebrish is redacted.

## Corrections after recording


- 2026-10-22, typed by Daniel: **Desktop only.** The output mode toggle already exists. Make it
  easier to manipulate: integrate it with the system tray icon and add shortcut bindings for
  toggling the output mode. This replaces what the note says about output modes where they differ.


## Transcript


[0:00:00] Okay, so this is going to be the first installation of the Hebrish app podcast. I don't actually intend to launch a podcast for this project, as in, I don't think there's any reason that this, this code switching project should have a dedicated podcast. But what I am going to do is a multi pronged use of this voice note, which is that it's going to be presented on the website as a podcast for anyone who actually wants to listen to an update about what the project is or an explanation. And I'm also going to use this to gather notes and context data for the next few sprints for my AI agent, the esteemed Mr. Claude Code, who is Claude Opus 5.5 is starting to scare me. It's like it's the first model that is just like prodigiously good.

[0:00:47] It's like it makes me feel very stupid. I'm using it and it's like I can't keep up with it. It's so fast and it's wonderful how quickly it's been able to help me iterate through this. So I'm going to explain basically what this project is, why I wanted to do it, and then I'll get to what's on my mind in terms of features. So the second part of this is actually instructions for Claude because I'm going to pull this into the part of the repository on GitHub where we have the I like to build in public and usually I'll have in my GitHub repos, my workspaces, I'll have like a folder for project management where I almost always use this voice workflow.

[0:01:36] I'll record it, then I'll have sprints, decisions and all that kind of stuff. And in this particular project I'm just going to put that in public, including these voice notes in their original. So that's, that's the purpose of the second half. The first half is just explaining to humans or AI agents, whoever you are, what this project is. So I began using speech to text technology coming up on two years ago I began using Whisper, which is OpenAI's open source speech to text model, an exceptional ASR model.

[0:02:15] And I'm going to assume for this podcast I'm going to just try de jargonize the tech a bit as well. So ASR is automatic speech recognition and that's just me. It's the basic speech to text model. And I've been using Linux for going on 20 years, something like that. I'd always wanted to use speech to text and I mentioned in my other online projects.

[0:02:43] I'm very open about having ADHD and I mentioned it in this context purely because I feel like these tools, tts, Text to Speech and Speech to Text are for people with neurodivergence. I feel like we're overrepresented in people who just think these tools are the best things ever. And I'm definitely in that category, which is, to my mind, quite interesting because of the fact that there's such a deep lineage of these technologies. Speech to Text and Text to Speech have had an assistive lineage for such a long time. And people with disabilities, people who can't type, the elderly.

[0:03:25] And I think it's actually really cool to see that. I would never have made the connection until recently that neurodivergence is part of that population. But maybe we are. Maybe we're under that umbrella along with people who just find it generally helpful. So I tried Speech to Text, you know, a few times, different projects, and basically until Whisper, it was, I would say, virtually unusable.

[0:03:50] I mean, you could. It worked. There were some earlier versions, but it just wasn't. It didn't cross that bar where this is actually going to save you time. And if you don't cross that bar, it's worse than useless because you're just going to go back to the keyboard.

[0:04:07] So Whisper came along. My wife was in the US around Thanksgiving two years ago, so I had the place to myself and it allowed me to. I think it was very. This was the. This was the week where I became a speech to text [unclear: convert?].

[0:04:22] And I told Hannah that when she comes back, she's gonna find me talking into my phone constantly. Because I discovered this new app and I've decided that I'm never gonna type again. I'm just gonna do this. So I did that. And it was great to have the house to myself, wander around the kitchen talking, getting all my ideas and to do lists out and not feeling, you know, not feeling like anyone was listening because I was literally home alone.

[0:04:52] So when I saw that the technology had matured so rapidly and to the point that it had my next, I began the process of basically trying to find ways to use this across devices. So on the Linux desktop. Linux always has that weird sort of feature of being where most of the prototypes happen and often, paradoxically, where the finished tech actually comes last because it's the smallest market. But there were apps and I began using Whisper on my phone. And over the course of the past couple of years, I've been developing prototypes for My own use because as many great speech to text apps as there are, I always find that there is just UI quirks that I want.

[0:05:47] So that's why I've been prototyping. But the Hebrew thing specifically is. So when I began using Whisper day to day, there's an app called voicenotes.com I don't know if they actually use whisper anymore under the hood, but that was the first one that used it that I got excited about and you know, I began using it all the time and you just everything, email drafts, prompts for AI tools a lot because it was. That's where I began getting great results with AI. I found that voice is so much quicker than typing that you can just record all the, what I call context data, all the background about yourself that is essential to getting a well rounded answer.

[0:06:36] And it was just far quicker than typing it. The obvious things anyone who's used speech to text in Israel will tell you this is that you'll find that it won't, it'll start, it'll struggle with the Hebrew terminology. So the reasons for this just to again provide a technical overview as much as an introduction to the idea is that you'll have words that do get transcribed and that throws a lot of people off. So you'll see Shabbat, Kashrut and basically ASR models, the big models like Whisper, which was the first major open source ASR model, are trained on a just huge corpus of speech. And the general understanding is that a lot of it is just YouTube being dumped, like huge amounts of YouTube videos, which is why sometimes the earlier versions of models would hallucinate stuff like thanks for watching the video, because the training was many, many hours of audio where probably a lot of YouTube videos ended up like, you know, signed off like that.

[0:07:47] So if you pull out a huge corpus of general English videos from a source like YouTube or wherever else you can find them, you're going to come across words like Shabbat. So basically the extent to which Hebrew words are going to be reliably transcribed depends to what extent they're in the general. In the general circulation of words in English, bias towards American English and content that winds up on the English speaking Internet. And that distribution doesn't extend to a lot of words that English speakers in Israel would use like shuk, bituach leumi. The further you go down that long tail, the less likely it is that it's going to be in the stock app which is trying to provide transcriptions for all of English.

[0:08:45] And we have, you know, is you're always going to be every word in Hebrew that you wanted to recognize and sounds like something in English is fighting inside of the model. Because the models are essentially predictive tools. And when you speech, when you speak. Sorry, it's looking at your phonemes, the sounds you make, it's not literally understanding. It doesn't have a concept of words per se, and it's finding matches between those patterns of articulations and words.

[0:09:23] So even if it's not well represented, the niche Hebrew word is always going to be displaced by something that sounds like it in English. That's cognate. The additional challenge in Hebrew, of course, is that when you pronounce a word like, we're following Hebrew phonetics. So the code switching project is basically started out. The first time I did it, it was a fine tune on a whisper.

[0:09:56] And the training methodology is essentially. And this is where it becomes tedious. Reading sentences like I need to go to the makolet today. And the. You create a data set in which the.

[0:10:10] You have your voice recordings and a ground truth. The ground truth meaning that the model receives the correctly transcribed version of I need to go to the makolet, spelled M A K O L E T. And then you train the model. And training the model means that you're taking an existing model. You're not starting from scratch. You're taking Whisper or the latest version of Parakeet, and basically changing the internal weights of the model, changing its internal weight distribution, which is basically a normal language, a way of exposing it to these new words.

[0:10:55] The challenge in doing this is that you are a drop in the ocean. You are adding a drop of weights about makolet and bituach leumi towards a model that has like hundreds of thousands of audios in its training data. And the weird thing is that the weird potential pitfall in this particular process is something called overfitting or catastrophic of forgetting as well, whereby it can get so well attuned to these niche words that if you say something like, I'm trying to think of a word that sounds like makolet in English, I need another example. I don't have one off the top of my head. But you'll have the inverse problem.

[0:11:40] It will start predicting code switch words for. For words that are in English. So that's why the training, the training mixture for this particular model contains words that are neutral English sentences. So I say, I'm moving the table lamp to the couch, which doesn't have. There's no training target there.

[0:11:59] It's just A stam sentence code, switching stam, and those are in the training data set. So that in the purpose of shifting the model a bit towards learning the code switched vocab, it doesn't end up forgetting how to process normal text. So there's a few things in the. In the project so far.

[0:12:27] The fine tune is based on Nvidia's model called Parakeet, which is a 700 billion, sorry, 700 million [0.6 billion] parameter ASR model, lightweight model. And the reason I used this as the base was that my wife and I moved apartments a few months ago and since then we have just been, you know, moving boxes and I've been using, for the first time in my life, my phone more than my desktop. And getting ASR models to run on the phone is still challenging because even if you've got the best flagship phone on the market, fundamentally it's a small piece of hardware. So on the phone the challenge is what's the smallest model you can get that's not going to be rubbish? And Parakeet is a good model for this because it's quite small, it's quite light and it's quite good.

[0:13:21] Nvidia have done something that Whisper, which is OpenAI's model, hasn't really done. People have tried to bring it to the phone through, you know, quantizing it. And I have been using Whisper, my own fine tune, on the phone and haven't had great results with it. And the first time I found an app with Parakeet, I was just like, whoa, this is the one. This is exactly what I want.

[0:13:46] It's fast, it's accurate enough. And I immediately saw this, this was a much more promising basis for fine tuning than Whisper was. So I think they both have value. Qwen also have a model which I tuned yesterday, fine tuned, they have an ASR model and the direction of the project is that I want to have the training plan as such is to have one model for maximum performance, meaning the the highest accuracy possible for running on servers or desktops, GPU acceleration, one model for, you know, the everyday driver on your phone and finally one for small devices and one for streaming. So for streaming, that's why I'm currently Nemotron by Nvidia is a streaming output model and I'm going to update that with the data set to get one first good version trained of that, because this is where I'll transition to the second part of this audio note.

[0:14:57] And there's a few. The way I use these every day straddles a few different use cases That I think a lot of the problem in speech interfaces to date or dictation tools has been that people are trying to. It's more a UI criticism than anything else. There's a bifurcation between long form and short form. So people will roll out voice keyboards and people will create transcription tools intended for long form processing.

[0:15:32] And I don't think that they really need to be two apps. And I always lean towards the principle that I'd rather have one app that does multiple things than two apps. At least. At least in this case. So for Hebrish, just before I get on to talking about the sort of UI backlog for us, explain the models a little bit.

[0:15:57] So Claude actually coined the terms. I wanted to have one name for each type of model. And what I did over the course of the past week, this has been a bit of a crazy, frenetic development period. But I would say that a large part of my motivation or what's driving me to do this work in very rapid, in a very rapid burst is so we have, my wife and I have a son. He is a year and a few months old and we found ourselves in the emergency room twice in the last month.

[0:16:34] And I guess speech recognition technology I find daily now more helpful than ever. When you're holding a squirming, you know, child and you're trying to clean up the place and you're also trying to figure out what you need to respond to an email, voice to text is just by far the most efficient way to do it. So it's become even more indispensable since I became a parent. And when we were in the, you know, in the, in the emergency and talking to our health fund, I realized that this is, this kind of tool could actually help a lot of people. When you are in those situations, you don't have time to, you know, go to your keyboard if you're looking, if you're trying to message someone about an update about your kids or talk to the insurance or someone who speaks English, you're not going to have time to fix mistranscriptions in models.

[0:17:30] So I guess my motivate, my. I would say that my motivation here is primarily I want to have a good tool for my own use. And I genuinely think, and I hope that this will be useful for other people.

[0:17:44] Regarding the training composition, one more thing, and this is going to be a pretty thorough voice note at this point, I'm looking at the, at the clock going by here. So when I began training the code switching sentences and because this Is, as I mentioned, something I want to, it's primarily, it's something I want to have for my own use and if other people find it helpful, great. And I'll try to accommodate, you know, different usage patterns. So the other things that I find, you know, I just kind of made a list of what does Parakeet and Whisper, what do they get wrong? What's standing between 90% good and 100% good.

[0:18:29] And that's the gap that I feel like we're, we're in at ASR, we're seeing at the moment plugins and MCP becoming very mature. So looking at ChatGPT, finally there is an email tool, there's a drive tool, there's a docs tool. So you can easily dictate into one of these apps and then say, great, send that off to send that as an email to my boss. And that's taken a while to reach consumer apps. And it's a very big deal for ASR models.

[0:19:04] The, the defaults has traditionally been the baseline. The baseline performance of what an ASR model does is it translates phonetics into letters on a screen. There's no, there's no, there's no rule written in stone that says an ASR model will add punctuation, will add capital letters, will add sentence boundaries, will add paragraphs. So all these things are not written into the fundamental logic of an ASR and they've just been integrated as they've improved. There's bolt ons at the moment in terms of S1 Mini by Super Whisper, a post processing, dedicated post processing layer.

[0:19:54] That's one direction, that's another direction that we're seeing at the moment. Moment. And there's also multimodal models, so omnimodal, which are models that can process audio and can process text. And you can write a prompt that says something like this is the, the audio you've received is a shopping list output this as a shot in a shopping list format. And that, that to me is a very appealing implementation.

[0:20:26] And it would have said until recently that I think that's going to just be the way and ASR is going to go. You know, it's going to be yesteryear's technology. But the other method seems to actually still be going very strong. The other method is that an ASR model is paired with, traditionally paired with an LLM and that second re-pass logic is the kind of cleanup step which can also do reformatting.

[0:21:01] So what I'm trying to do with my model and this is a architectural decision More than anything else is. And it's experimentary. I'll say that at the very start. And I'll also say that it's an idea that people might take issue with. Not everyone will think this makes sense.

[0:21:28] It just is what makes sense to me at the moment or what I'm exploring with in this model. And that's that can we take a model like Parakeet and we're doing the code switching training, but can we push that a little bit further? What else is, you know, what else do I see as problematic? So for Parakeet, particularly when I began using it, I noticed that it was output disfluencies. So disfluencies are those things.

[0:22:02] Hesitations of speech. Another thing is false and word repetition, a full start being that you say I want to and maybe you never finish the sentence repetition, word repetition being I'm going to put the tomato tomahdo in the fridge. You know, you're out there, you're scatters, you're holding up a phone to your face. And the desired transcription is I want to put whatever I just said tomatoes in the fridge. The other one.

[0:22:40] And this is, this is again Parakeet specific was. And this is Israel specific as well. If you say the coast cost me the coast, the coat cost or the falafel cost 20 shekels. Now to my mind, for my personal preference, if that sentence once is going to be in a WhatsApp or it's going to be in an email, I can't think of a situation where I would actually want to see shekels written out like that. I would prefer 20 NIS.

[0:23:14] Now people might disagree with that. They'll say I never write that. I always write shekels out. But again, as somebody creating this open source project, I guess I have the luxury of being able to build it for my personal preferences, that's one of them. And there is a couple more.

[0:23:32] The lack of paragraph spacing is one that I've found very strange that models don't do that. So I've recorded it. I created a data set pair for paragraph spaced text. So it takes a long form ground truth, let's say a few paragraphs together about, I don't know, a DIY project, something that goes on for a few paragraphs and Parakeet will return that as sentenced a sentence blob of text. And I say right, but and this is why I mentioned the post processing steps path.

[0:24:10] One is we rely upon a post processing small model to do all these after steps and we set separate The ASR level, we separate hermetically between ASR being responsible for getting accurate rendition of text and everything else, including paragraph breaks, for what comes next. Now, my beef with that argument would be that the moment you even add sentence boundaries and punctuation, which Parakeet does, Parakeet has already gone beyond just rendering text, it's creating sentences. And I would argue that paragraph breaking has been a big blind spot in ASR. That's a fundamental property of the intelligibility of text. And I would say arguably barely less essential than periods.

[0:25:09] And so that's a small data set. And again, the question is whether a small data set can nudge the model towards doing that. I don't know. There might be some architectural thing that makes it impossible. I haven't thought of.

[0:25:23] I'm far from. I'm an experimenter and a builder and I don't know all the inner details of how these models work. It's very complicated stuff. So that's an experiment to see if that can be done. So that's another small data set.

[0:25:40] The other small data set is the inclusion of technical vocabulary. So you know, stuff like I'm running a Docker compose script, I'm running a Kubernetes cluster, and finally I have like my own little. I have a small data set I think called. I don't call it Danielisms, but it's. It's like my own quirky vocab that I've developed and things that I see it getting wrong.

[0:26:07] So I have a podcast called My Weird Prompts, which has hosts called Herman Poppleberry and Corn. It's an AI generated podcast. And because those are commonly botched, I created a small data set, very small, just with the things I'm seeing it get wrong again for my own benefit. So that will include that I'm going to get to at the end of this, the restructure that I did today. So for a while I wanted to have a voice clone because I like to pull pranks on people and I like to, you know, do a voice agent to call up a friend.

[0:26:48] If Mike ever listens to this, he's probably spoken to my voice clone before. You know, voice cloning, of course, very ethically, not ethically, but, you know, huge potential for black hat use and fraud and whatever. And I guess I take the view that I have a YouTube channel. I've. I've got hundreds of hours of my speech on the Internet.

[0:27:09] Having seen how easy it is to clone anyone's voice, you can literally clone a voice from 10 seconds of YouTube. So if you want to clone anyone's voice, you can clone their voice. So I want to have my voice as available for my own occasional use. But when I was doing this, I was thinking, hang on, can I take the data set I'm building for code switching and use it to create a TTS voice? Now the big limitation that might be the elephant in the room to anyone listening is that not many people have Irish accent in Israel.

[0:27:48] So a TTS that renders code switching text correctly but in an Irish accent is kind of a. It's a, it's a niche appeal. Put an acquired taste, you might say. So I realize that I'm not, I would say I'm not the ideal. I would say it's not the ideal baseline my voice, but rather just, you know, have it out there.

[0:28:15] It can be so that there's an experimentary TTS that is called. Hang on, what did Claude. I was arguing with Claude. I said Claude. I need more imaginative names for the TTS one.

[0:28:27] What do we decide on in the end? I'm scrolling through my Claude here and [name redacted]. [name redacted], yes. [name redacted], no, sorry. [name redacted] is the tech model.

[0:28:35] Gets the model naming at the tail end.

[0:28:45] I'll have to come back to this. It's going to be a one take, one take episode. Meorav. That's it. I thought that was clever because Meorav, you know, for those who aren't in Israel means there's a famous dish called meorav yerushalmi which is like, you know, organ meats, basically, all this stuff thrown together.

[0:29:07] And I guess that's kind of what code switch speech is. So Meorav is going to be the TTS model which I trained a first test run on yesterday. And for those who want to know, just are interested in knowing how the data sets are structured. So the initial thing I was, I was doing. So I was recording my sentences earlier this week and I was recording the code switching data set sentences like I need to go to the makolet to buy milk.

[0:29:36] And then I was recording the text sentences and the other ones like I need to, I need to check the Docker memory use. And my initial idea was that I'd create a Parakeet-tech and a Parakeet code-switching. And I was doing that because I assumed that if I were to add the tech sentences into the Hebrew sentences that the accuracy of both would suffer, that the cleaner approach was to just have it split like that. And we did a test evaluation A few days ago, where I called it initially the kitchen sink, I told Claude, let's create a kitchen sink data set. Just lob it all together, train it all up and see see how it does on everything.

[0:30:27] And to my surprise, the accuracy on tech and on and on the Hebrew words, neither degraded. So the question that I have open is really, well, this will be. It's whether that's, you know, the kitchen sink one which is called Sabich is the right one for. As a default for like what's generally useful for people who work in tech and are code switching. It's an obvious choice and the question is if you don't work in tech, does the fact that this has a few samples about vocabulary you won't use degrade it, or is it something that you may as well have in the model?

[0:31:07] And certainly from a maintenance standpoint, it's much easier for me to make, maintain and ship one model than it is two. So I would say the long term, my long term preference would definitely be to collapse for Hebrish at least. But for personal distribution I do want to ship a models that are just have the tech vocab because for people who don't, who aren't in Israel, I feel like it's, you know, it's, it's a more logical fit just to have the technology run. So that's going to be going out as. What did I just say?

[0:31:43] I'm totally confused by all the names. Claude has come up now. Flipper, I think it was Flipper [a personal model, not part of Hebrish]. Anyway, I can put a link in this episode for the personal one and that's the personal personal baseline plus tech for each of these. The reason I'm giving them creative names is that they represent some.

[0:32:04] So Sabich is kitchen sink; Jachnun, if we maintain it is pure code switching. So it doesn't include the tech data set and its training doesn't include my niche vocab. Just my own personal words and open question as to whether the experimentary data sets, the paragraph inference will be included in that one. My preference at the moment is that Sabich will be the kitchen sink. Really the kitchen sink.

[0:32:32] It'll have all the things and all the experiments baked in. And Jachnun, which is the just code switching will be more conservative. Just focus on the code switching vocab and maybe leave out everything else including the paragraph inference. And as I said earlier, whether they'll be still be maintained. Whether Jachnun will have a life is an open question.

[0:32:56] The naming that I followed is the reason I wanted to have a sort of series name is because within each of these, each name represents a data set composition rather than a specific model. And within each family I'm going to experiment with, you know, can we have a version for the desktop? Can we try run the data set, the fine tuning data set on Qwen, can we try it on a different ASR model that comes out? So the name refers to the series and what it contains instead of the actual iteration which depends upon which ASR model is being trained.

[0:33:35] Well, I think that's a lot of ground that we've covered already. I've got to get onto the implementation part of this for Claude's context, but even this context will hopefully be useful for the AI agent and licensing is free for non commercial use because I don't know, perhaps someone will find a good commercial use for this. And if I really want to keep. As I've been building up the data set, it's occurred to me that, wait a second, we have Ashkenazi pronunciation, we have Sephardic, we need different accents, we need different genders, we need the. There's so much religious vocab like all the masechtot of the Talmud, all the major sefarim, all the partial, all the parshiot major rabbis that if you think about what would be useful to have.

[0:34:34] And the other thing for those who, you know, who don't haven't tried something like this before, is that when you have a word that we want to add to the fine tune, let's take makolet or kind of the classic example I use over and over, I don't record one sentence with, I want to go to the makolet. Ideally it's 10 sentences. And the other thing, and these are just some of the objectives for the fine tune is there's a big difference. This is where there's a significant difference between data collection for the TTS model and for the speech to text. For speech to text, you actually want to have a data set that is a bit scrappy because the whole idea of this is that it reflects real world use.

[0:35:26] People are trying to dictate something in the shuk with the bar blaring music in the background, with other people conversing around you in different languages. And all of those involve discrete challenges for ASR because the model can't necessarily distinguish between the intended and non intended speaker. You know, there's no built in heuristic like that in the model itself. You might have wind noise, you might have honking, you might have a baby crying. So I'm actually when I'm recording them trying to. Oh great, this is noisy.

[0:36:04] Let's record a few samples here. And the idea is that as you record these iterations of different words in different conditions that the model gets more robust. It doesn't collapse when you say one of your code switching words when there's a big gust of wind and the audio is bad to begin with. So that's the augmentation to get back to the licensing idea. This is a non profit venture.

[0:36:29] It's something I wanted to have for my own use and benefit other people, both in Israel and the Jewish world. But of course devoting time takes money. Also training all of these takes money fine tuning them. Developing the app takes a lot of time to record the samples. So I wanted to leave the door open towards a mechanism that people could either support it or license it if it could be potentially useful in a context like telephony.

[0:37:00] So that's it at the moment it's just open like that and the data sets are Access gated on GitHub. On hugging face. Just because I know the Hebrew one, I'm not unaware of the fact that there is for all of this. There's a potential for people trying to find a data set with this data composition of code, switched English, Hebrew with bad intentions. Put it like that.

[0:37:26] So it's a voluntary security measure from my side more than anything else.

[0:37:35] And I think that's about it in terms of apps and user interfaces. So currently it's biased towards what I'm actually using. There is an Ubuntu app, there is a Android app at the moment initially provided through F Droid and I'm looking into getting it published on Google Play. For that I have to make just a few changes to little things actually get it reviewed, record a demo. It's a.

[0:38:03] You know, they have a. They have a submission process, but I want to do that for sure. And Windows as well is a thing. So for iOS it's a little bit more complex the path both because the weights have to be. The inference on iOS is a bit different and it's got its own pathway.

[0:38:20] So that's the more involved migration. But it's of course very important. It should be available on both apps 100% and that's a work in progress basically. But again, something that costs money. There's.

[0:38:32] I looked into the plan for it. It's a little bit more expensive than Android to ship it out and for the moment I have to obviously keep my investment time and financial in this reasonably capped regarding other speakers and different things. So for this particular corpus and this particular use case, I'm thinking about all the ways people pronounce Hebrew, the different accents. We have Yeshivish, Haredi, Ashkenazi, Sephardic. And the idea is that I want to have all of those represented and some of this might require.

[0:39:10] It's very hard, what I noticed, recording these samples. It's very hard to focus on tagging and recording all at once. So I try to. I have a. Claude built a little custom recording app for me for actually recording my samples in, which is fantastic and has settings where I can say baby crying and that's how the annotation gets noticed. But it's very hard to do that reliably when you're just trying to read and pronounce stuff correctly and audibly.

[0:39:38] Regarding the actual data set plumbing, while I was mentioning that. So what I'm trying to do is come up with a way whereby. Because there is huge overlap between the TTS and the STT, the difference is that text to speech, you want the opposite of the STT conditions. You want a clean noise floor, you don't want background noise. Because this is going to be.

[0:40:02] This is a training data for the tts. So it's the same.

[0:40:08] I'm trying to train it on the vocab. But those samples are only good for the STT set if they're quiet. If they're noisy, they're fine for the STT data set, the ASR data set, but not, not for the TTS data set. So that's. Claude is the.

[0:40:27] As I said, Opus 5.5 is the genius that I'm trying to explain what I'm trying to do. I don't want to have to read all these mundane sentences twice over. And we're creating a. Basically a plumbing system whereby my voice. I have a little.

[0:40:44] I have an. I have a mode on the app that says am I doing tts? Am I doing it for the TTS model or for ASR? And depending upon which I choose, the clips will be routed accordingly into the different data sets and the training then will be done on the correct clips. So the final thing I'll talk about the UI itself.

[0:41:04] And this is at 41 minutes and 15 seconds. This is where I get to the actual instructions for Claude. So here's. I guess what I'm currently thinking. My principle for voice tech, having used it for, as I mentioned, full time for a very long time, is desktop use.

[0:41:24] I think a macro pad is the Best way to go, because I think you really need. The simplest way is push to talk or what I call the tap tap pattern. And that works. But you also need buttons for ideally, stopping, retaking. These are things that become evident and apparent when you use this all day, every day.

[0:41:48] And I think I've narrowed it down to about six buttons, which is more than a traditional USB foot pedal provides. Some of those are, I think, exit, sorry, cancel, eject, retake. And something Claude pointed out to today very intelligently was that the best design is probably that none of these or these can all be mapped onto custom keys, including the escape one, so that you never have any conflict with global shortcuts. And that's a big case for a macropad whereby you can map the escape key so that there's no conflict with anything else on the os. If you're using system level speech to text, which is what this is, if it's not application scoped, you've got a greater chance of having keyboard shortcut conflicts.

[0:42:43] I usually use F13 because it's recognized as a valid key and then I map my USB devices onto that. So like F13 is my button and if I'm in, if I'm. If I'm in tap tap mode, I hit a little USB button, a $5 device from AliExpress USB HID button that sends out 13 and that's bound to it. So I think the design in the settings and shortcuts should accommodate a basic setup provide the user uses Enter and Escape because that's easier to do on a laptop. And an advanced shortcut binding option whereby if someone has dedicated hardware like a macro pad, they can remap all of these onto whatever keys that they want.

[0:43:34] So that's number one and then number two is for the Android. So Bluetooth support is very, very important. And if I'm in the noisy environment, using a Bluetooth microphone, we added the ability to change the microphone input source, that's key. And the other one that I would find helpful is a button binding. Now this is tricky.

[0:44:03] So I have a, I think it's a Yealink Bluetooth headset and it has a button. On Android you can use a tool like Intercept. There's an interceptor that will intercept and map. Now what I would like is it's only one button. It's one button on the, on the device.

[0:44:23] Then you've got things like the micro dos, that thingy that is probably the best equivalent of having a macro pad for Android. But at the first implementation, just assuming the user has one button at their disposal. What would be great would be being able to use that button with the app, which would be some way by which the button can be bound to start, record, stop. That's the fundamental. If there's nothing else.

[0:44:59] And I think that that would have to be the tap, tap, as I call it, because holding down a button on a, you know, on an earphone would look very weird. So I think that's the better pattern there. And then the later, fuller implementation can be looked at. That can be a later thing to be discussed in the desktop ui. So I would like to document the following, what you could call canonical usage patterns.

[0:45:35] And I think it's. The idea here is to. Is to find a way to map these onto models because each one biases for a different model. So the first one of these, I'm just turning up the aircon here. The first one of these is.

[0:45:51] And that's one of the things in my data sets, the. I'm turning off the aircon here. Non-diarized speech. Speech that was the model can determine it was not intended for transcription. That's another one, the experimentary one.

[0:46:06] So the first is, the first usage pattern is I'm typing into Claude code and I'm using on Ubuntu the text injection at the cursor level. And what we're currently doing is it's dumping. We updated to a few settings, normal, slower, slowest. The most impressive implementation I've seen is actually the one in Claude code. And I think that it's using Deepgram under the hood.

[0:46:35] And what's impressive about it is that it's streaming. So it's streaming speech to text. But it does one more thing beyond that, which is that if you go, if you finish the sentence and then it determines that what it previously wrote was incorrect based upon the new context you've added, it will like magically. I'm going to call it magically because it looks like magic. It rewrites the text, the previous text it corrects on the fly, which is very cool.

[0:47:08] And I was asking Claude today, what on earth is this technology? Is it just a streaming model or is it an additional construct? And I think it said it's an additional. It's an additional construct, but the building block to use that construct is a streaming model. So I realized when I.

[0:47:27] When it explained that, that this is a reason that the streaming model, which is the one based on, losing track, Nemotron, which is Shakshuka. So Shakshuka is the third model that's the streaming fine tune both on top of Shakshuka and it's the kitchen sink version. Another naming convention could be that we have Jachnun streaming which is the Jachnun data set Hebrew only code switching only on top of Nemotron, and Sabich streaming. But for now it's Shakshuka. It's.

[0:48:17] It's the third member of the family just for streaming. We might revisit that later. I feel like it's. It's actually better to keep them apart. I think the difference is significant enough that it's better to have that as a separate model.

[0:48:29] But it means that there isn't currently a Shakshuka. It could also be Shakshuka all and Shakshuka code switching that we have a Shakshuka variant that is Nemotron only on the code switching data set. That maybe is the better way to do it down the line but that doesn't exist yet. Right now the Shakshuka is the is everything or as many things as can be included for that baseline.

[0:48:58] So that what I think would be makes sense is that that model typing at the computer has a defaults will use Jachnun which I think also changes how the setup should go in that right now it's like you should choose your model and I think the better presentation to the user is download models. We can still have recommendations for your. For your hardware but the baseline assumption is that on the desktop at least they'll want to have a streaming model and a non streaming model, both of them. And we should keep the trainings in parallel. So every time I have a significant amount of new training data the process should be not at the moment I'm just seeing, experimenting, seeing which works, this works, that works which creates divergence.

[0:49:59] So it should be a much more standardized process by which there is a defined V2. Next one could be called V2 and there is V2 for Jachnun, Sabich and Shakshuka all at the same time approximately with the same data set. So there's no divergence. They're all kept up to date in parallel. And then for my own model, whatever is called flippers, flibbers [the personal model's name] that can also be done.

[0:50:28] Probably best to do it at the same time just for convenience. But doesn't have to be on the same release cycle the second mode. So this is where I think transcription and dictation have to be carefully thought about in terms of how to present them. There's two very different things you can do with transcription one is that you record at the computer at the device and you sit down to record something long. So let's say it's going to be a 15 minute long note.

[0:51:01] I'm just going to explain the rationale even though this is getting into a lot of detail. But when I am doing streaming at Claude code, if I have a big say, this note, which would be even if it didn't have the preceding content, would have been a lot of information. I don't want to just have that appearing. That's where I lose confidence in. If it's just going into Claude code in the terminal, if I've seen Claude, there's a limit on the input text.

[0:51:31] I don't want to lose. If I'm going to spend an hour explaining all the ins and outs of an idea, I want to feel confident that the source, which is what's valuable, the audio is not going to be lost, which is why I'm recording this on my phone in a sound recorder app. And that's something I do habitually. So the. For the long form transcription, the two pathways that I see as options are or as user interfaces that make sense are you do long form transcription in the.

[0:52:04] In the app itself. And again, this is where the model matching becomes really important. That by default locks onto the parakeet fine tune and all the inference scaffolding around that is optimized for long form meaning it's essential that it can reliably capture notes. It can say on the app like up to, let's say 90 minutes or whatever the maximum that can be supported that requires chunking local storage. If it's offline, it's not trivial.

[0:52:41] And it also requires the longer when you go out to this length, you need to think about API limits, upload limits and doing stuff like VAD down sampling as you capture the chunks. So that architecture is a bit different. The second one is I think almost a cleaner one which is just file based transcription. You upload a file and it does the inference over that what I think would be the most logical one. So we've added today a feature for local storage for the dictation history.

[0:53:19] I think ideally support to the cloud, support with the cloud. I want to have a method for seeding words. And what I'm also creating, and this is more a project note my idea with the dictation history is that I'm going to mine my own dictation history, which is thousands of words per day, minimal as a way to identify things that the model is still Getting wrong and then pinpoint words from that that need to be the need to be added to the training data set so that the data set actually the transcription history actually becomes a source of iterative improvement. And maybe in the future, you know, there could be an option whereby people can share anonymized histories of their own. Probably no one's going to want to do that, but you know, that could be an option for.

[0:54:08] Because I can still it's very easy for me to see as I use a tool. Ah, great. This is, it's getting this right now. Why is it still misspelling that we need more data there? So I think that will hopefully make that a lot easier.

[0:54:21] So regarding the integration was the tool. So right now when we're doing the transcription into the app and it gathers the history and it puts it on the clipboard, that's the text injection workflow. And then for the long form workflow, I think it's the ideal thing. The ideal use I would have for a long form would be maybe something more akin to a document editor, but really a self standing module. You go into the dictation mode, that mode's running.

[0:54:59] You can either choose a file or send a recording. It does it, it can automatically save. And this is where in the future, with the cloud backup support that I want to add, I'm going to add it to my own account as a beta test. And then potentially in the future it could be a. You know, users could actually sign up for this as a SAS tool.

[0:55:21] But for now I'm just going to use it for my own testing. And probably an ideal UI for me would be like it transcribes and it auto saves. Because the first concern is always data loss, data loss prevention. Great, we've auto saved now I might want to tidy it up a bit and then hit save. And then maybe like you know, one other idea that I had earlier for I thought would be a great integration would be for this mode.

[0:55:48] Create new Google Drive, sorry Create automatically creating new Google Docs based upon you can get assigning the transcription a name.

[0:56:00] So this is a feature that's like the voice Notes feature. And I think that for the, for the default mechanism it should be recording and putting it on the clipboard. The clipboard. What I did in a previous implementation was I had a mode for. I had two modes that you could choose for the app.

[0:56:24] The default mode was we'll put it on. This is for Ubuntu. We'll put it on the clipboard and we'll Inject it. The rationale there is that the Clipboard serves as a backup. If you are doing text.

[0:56:35] If you're relying upon text injection and you accidentally move your mouse outside of the whatever the target, that's a way to lose the thing. And the easiest way to do that, what I've seen done on Android is I think this is implemented in this app, is if it detects that when the transcription returned, you weren't in a text field, the overlay will show a clip, which will show a little text insertion thing. So you can pop it in there.

[0:57:11] That's one thing. So for.

[0:57:16] So that was my default mode. Was that. And then I also added a mode for either or. So one was just Clipboard, just put it on the clipboard, no text injection.

[0:57:27] And the other one was text injection only, no Clipboard. I don't actually see uses for them. And I think the philosophy I'd like to follow in general for this is slightly deterministic. Meaning that again, this is just my philosophy. Too many options for a little.

[0:57:46] Every little thing can be distracting and unhelpful. And for the moment at least, I'd rather make just an executive call on this that we're just gonna support always Clipboard as a backup and.

[0:58:03] Or one sec, I'm gonna retract on this. Which is why this voice note is different. I do actually now we should have all the modes. And I'll explain why in a second. If it's always going on the clipboard.

[0:58:18] If you record and we have a history, which we do recording all your recent transcriptions, searchable and you can see the last 10, you can always copy it out of the app. That's a reliable fallback. The reason that the Clipboard thing can become annoying is you start dictating, you copy something from an app and before you pasted it, the transcription comes back, overwrites your clipboard. So there is actually a reason an edge case where people might want to have the deterministic setting or some kind of a detection for that race condition in which it's. Oh, wait, the clipboard is.

[0:59:03] Has just. The buffer has just been filled. I'm not going to overwrite what came on the clipboard. Send a notification saying transcription held back or something like that. That's another.

[0:59:12] Just an idea for the future. Right now, I think those are the. Those are the. That's the kind of general shape. And then for Android, I don't know to what extent I would say for desktop, these are definitely viable.

[0:59:26] For Android, I'm not sure to what extent in a fully offline transcription mode could be achieved and I'm not sure if we have the local storage, if that's possible without any additional. I know the allowable file access permission is a blocker for Google Play so I don't know if the default one allows reliable local storage. I think it actually does in which case it could just be safe to save to local memory. But of course in a phone you've got you're a bit more constrained the question as well. One other side question is regarding audio recordings and my strong preference is that they will never be retained.

[1:00:13] The only retention of a recording, meaning when the user across platforms record something is for failure prevention like if the transcription fails, keep it maybe keep the last three, you know, in the future as if there is a fallback that would require a few back but otherwise it takes some space and it makes me uncomfortable to have to have that to have voice recording sitting around and eventually for the history we should have, you know, settings for that kind of history truncation as well. But for now I think those are the main ones. That's the project outline that is the next sort of jumbled up Sprint and I think for the UI for desktop needs to be closely integrated with the. With that layer with the system tray icon and for the text editor mode for long form dictation I think there might be components that can be used. I mean the ideal thing would be having a sort of very text editor like experience.

[1:01:23] The final thing that I'll actually. Two architectural things I'll tag on here just to get everything out in one go. Accessory layers, vad. I'm not sure if it can be implemented on Android if it's there on the desktop. If it's there should it be a toggle because fast inference is key.

[1:01:40] And the second open question is regarding a personal dictionary. So this is an interesting layer on Android. On Android the personal dictionary is exposed quite, quite liberally and I've always been an advocate for using these systems. You know, it's not people aren't going to create their own fine tunes. Most users are not going to do that.

[1:02:05] So my method of baking my own dictionary into my own fine tune is maybe that makes sense but it's not replicable for most people.

[1:02:16] I'm not sure how that is integrated to be honest and whether that could be integrated into the inference pass. So the user has either an Android we integrate with the user's personal dictionary or there's an option to do that and on the desktop and syncing across devices. And that's where if the cloud integration were to come in, that would be, that would be brilliant because that is a huge accelerator of productivity. If you use these tools every day, you'll notice that they, you know, you'll add your own personal dictionary list on one app on Android and inevitably then you use another computer, they're not there and you create it there and they're never quite in sync. So that's one kind of failure that I've seen.

[1:03:01] And another one is if anyone actually starts using this, which would be great. I think a brilliant feature that would work very well with my workflow would be report a word that didn't get transcribed correctly. So let's say you say I said burkade, Amazon and it didn't work. Either you just send the word or you send the word and note and that could pipe into a user submitted corrections training data set that gets piped into my recording app and I can then record. Final thing is for the recording app I'm sure I can find a few friends who would, you know, be happy to record a few sentences in different accents and whatever.

[1:03:40] And I'm looking at the moment for now, Hannah has recorded a few sentences. I have a little manual tagging thing. My general principle is I'd rather always the priority would always be gathering more training data and fixing up the annotations later before the next training. So the ideal thing is I think maybe the training app has is multi tenancy. There is a few users and based upon who you are, you're logged in as that's the annotator and then we can tag that, sorry, tag that speaker with their accent, maybe a short bio about them for credits and you know, contributor to the project.

[1:04:21] That's where that's what I'd like to have and we could probably even bake that in right now because I'm the only user. But I think I have a manual drop down for Hannah so I can, I can say that she did it, but probably better would be that she has, I can add her address to the whitelist and then her annotation pro. Her speaker profile is what gets added gender, female accent, U.S. background from Dallas in Israel for 10 years. And then we can of course the useful utility there is that the data set could be stratified based upon what accents we have, what, how many female, what percentage of the data set is from a female speaker, from the code switching and so on and so forth. So I think the final one, the initial quick and easy, quick and Dirty fix for the moment, for the possibility that a friend shows up one day at my apartment and says, oh, the app is great.

[1:05:14] Can I record a few sentences? And I'm like, sure. I'm not going to on the fly, create a profile for them and get on to Claude. So maybe like just a custom one, whereas a fallback I can add custom name, accent, gender and short description and then maybe they can be added to the annotation pool that way. And then I can figure out a login later if it becomes necessary.

[1:05:42] That would be a good enough patch for the moment because it would be fun just to go out to the field and say, hey, would you read out a few of these sentences for this app? It's free and you'll be contributing to other encouragement. English speaker is getting better dictation. All right, I gotta go pick up the little one very shortly. So that's my brain dump.

[1:06:04] All the ideas, all the progress updates. And if you want to get in touch, my name is Daniel Rosehill. I have a personal site, danielrosehill.com I have an AI consultancy, Carrot Cake AI, as in carrot cakes. And you can get in touch with me or through hebrish.app.

[1:06:21] H E B R I S H oh, that's the final thing. A small data set of our own identity. So hebrish.app should be in it. Hebrish should be in it. Because ironically, that doesn't get recognized currently.

[1:06:34] And the general principle being for hugging face. All the data sets and models related to the project are in the organization. All the GitHub repos that are for this project are in the organization. Not my personal account. Just to keep it properly segregated and.

[1:06:50] Okay, I really gotta go. That's it. Over and out from Hebrish. Daniel Rosehill. Progress update and vision for the next Sprint.

[1:06:59] Today, late October 2026.


## Spelling fixes applied


| Transcribed as | Corrected to | Kind |
| --- | --- | --- |
| Hebrewish app podcast | Hebrish app podcast | project name |
| So Hebrewish app should be in it. Hebrush should be in it | So hebrish.app should be in it. Hebrish should be in it | project name |
| through Hebrush app | through hebrish.app | project domain |
| for a hebrush, | for Hebrish, | project name |
| collapse for hebrush | collapse for Hebrish | project name |
| Over and out from Hebert. | Over and out from Hebrish. | project name |
| H E B R A S H | H E B R I S H | spelling |
| UI backlist | UI backlog | misheard |
| adhd | ADHD | casing |
| Speech to Text iheart | speech to text [unclear: convert?] | unclear word |
| Shuk, Batuach, Leomi | shuk, bituach leumi | canonical romanization |
| McCulloch today | makolet today | canonical romanization |
| the mikolet, spelled | the makolet, spelled | canonical romanization |
| the latest Russian parakeet | the latest version of Parakeet | misheard |
| McCullough and Batua KHLMI | makolet and bituach leumi | canonical romanization |
| sounds like Macaulay in English | sounds like makolet in English | canonical romanization |
| 700 billion, sorry, 700 million parameter | 700 billion, sorry, 700 million [0.6 billion] parameter | factual note |
| Quinn also | Qwen also | model name |
| Nematron by Nvidia | Nemotron by Nvidia | model name |
| let's take Macaulay | let's take makolet | canonical romanization |
| I want to go to the macaulay | I want to go to the makolet | canonical romanization |
| in the Shook with the bard blaring | in the shuk with the bar blaring | canonical romanization; misheard |
| a baby CRYING So | a baby crying. So | casing |
| Maserchot of the Talmud, all the major Sephora | masechtot of the Talmud, all the major sefarim | romanization |
| Hermann, Poppleberry | Herman Poppleberry | name |
| Herman, Poppleberry and Corn | Herman Poppleberry and Corn | name |
| my cloth here | my Claude here | misheard |
| is the is attack model | is the tech model | misheard |
| me Rav Yerushalmi | meorav yerushalmi | canonical romanization |
| So Mayorav is going | So Meorav is going | model name |
| Mayorav, you know | Meorav, you know | model name |
| to the Makola to buy | to the makolet to buy | canonical romanization |
| a parakeetech and a parakeet code switching | a Parakeet-tech and a Parakeet code-switching | model name |
| kitchen sync one which is called Sabik | kitchen sink one which is called Sabich | model name |
| Flipper, I think it was Flipper. | Flipper, I think it was Flipper [a personal model, not part of Hebrish]. | model name note |
| baseline plus text for | baseline plus tech for | misheard |
| So Sabih is kitchen sink Jaffnun | So Sabich is kitchen sink; Jachnun | model name |
| preference at the moment is that Sabiha | preference at the moment is that Sabich | model name |
| And Jack Noon, which | And Jachnun, which | model name |
| Whether the Jaffnoon | Whether Jachnun | model name |
| on Quin, | on Qwen, | model name |
| the Mike Personal preferences | my personal preferences | misheard |
| for Mike Personal preferences | for my personal preferences | misheard |
| 20 shackles | 20 shekels | misheard |
| always write shackles out | always write shekels out | misheard |
| see shackles written | see shekels written | misheard |
| between the TTTS and the SST | between the TTS and the STT | acronym |
| only good for the SST set | only good for the STT set | acronym |
| fine for the SST data set | fine for the STT data set | acronym |
| So that's. Plaud is the. | So that's. Claude is the. | misheard |
| principle for VoiceTek | principle for voice tech | misheard |
| on a Earth phone | on an earphone | misheard |
| Non diorized speech | Non-diarized speech | term |
| which is the one based on Losing Track Nemotron | which is the one based on, losing track, Nemotron | punctuation |
| we have Jack Noon streaming which is Jack Noon data set | we have Jachnun streaming which is the Jachnun data set | model name |
| on top of Atropa Nemotron or and Sabik streaming | on top of Nemotron, and Sabich streaming | model name |
| defaults will use Jacnoon | defaults will use Jachnun | model name |
| V2 for Jack Noon, Sabih and Shakshuka | V2 for Jachnun, Sabich and Shakshuka | model name |
| whatever is called flippers, flibbers | whatever is called flippers, flibbers [the personal model's name] | model name note |
| doesn't have to be wet the same | doesn't have to be on the same | misheard |
| Repass logic | re-pass logic | misheard |
| a better test | a beta test | misheard |
| a deal UI | an ideal UI | misheard |
| Grace we've auto saved | Great, we've auto saved | misheard |
| in Edge case | an edge case | misheard |
| my name is Daniel Rosell | my name is Daniel Rosehill | name |
| danielrosel.com | danielrosehill.com | domain |
| Carrot Cake. AI.com as in carrot cakes | Carrot Cake AI, as in carrot cakes | name |
