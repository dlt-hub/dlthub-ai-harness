# Hackathon

## Story
1. prompt was quite abstract "terminology consistency checker"
  2. wording (noun, verbs, etc.) is inconsistent across code, docs, skills. It makes hard to understand for humans and agents.
  a. technical challenge: keeping things in sync
3. generating the glossary
  a. automate the process
  b. merge sources: code, user workflows description
4. identify semantic inconsistency: use the taxonomy as source of truth
  a. use cheap entity recognition to flag potential violations when checking large inputs like full docs or all toolkits
  b. use SoTa LLMs to prune candidates
5. fix identified inconsistency: human-in-the-loop
- use locally as command in claude code session
- automated CI action

## Cool stuff
- intermediary files
- GitHub actions annotations
- logs of the conversation
- interactive experience
