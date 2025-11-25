# Some ideas around the DSL and contracts

We need to improve our beats system. Make it more structured / formalized.

The LLM still has a lot of control over the story, which is good for emergence, but is poor for reliability.

Characters are not generated via the tool reliably. Names may not be unique (i.e. duplicate characters). We need strict protections against duplication. We don't want duplicate characters, locations, inventory items, etc. Every minor character needs to come from the generator too.

Do we make it based on Python?


# Example Idea

High level idea of a scene or perhaps a group of scenes.

Start
* Prose block A
-- Transition
* Prose block B
-- Transition
* Prose block C
End


## Prose block A

Each scene, or a group of scenes, will be composed blocks. Each block will likely have sub-blocks.

Prose block A, Pseudo-contructor:

* Characters
* Location
* Purpose / Goal for the scene & characters
* Which plot beat is being addressed
* Number of sub-blocks (but this may not be known, it may emerge)


**comment**
Should the characters be objects with an inventory?

### Sub-block A.n:

The contents of a sub-block:

* An opening sentence / sub-scene if the start of a chapter / start of a book.
* A description of a location
* A description of the characters in the location
* A description of the technology
* Dialogue between characters
* Actions taken by characters
* Characters thoughts and feelings. Perhaps monologues / soliloquays.
* An ending sentence / sub-scene if the end of a chapter / end of the book.


**comment**

Sub-blocks are the fundamental building blocks of the story. They will have different functions within the story.

We won't need to have recursive blocks within blocks. New sub-blocks can be appended to resolve any situations. Books proceed page-by-page. So the mechanical flow is linear, even if the prose is non-linear. Our contracts, if we call them that, will proceed block-by-block in a linear fashion.


## Sketch

Example of a contract / use of the DSL:

Prose block A{
* Sub-block A.1(starting scene / description)
* Sub-block A.2(character monologue and set of actions)
* Sub-block A.3(diaglogue between characters)
* Sub-block A.4(character feelings and continued set of actions)
* Sub-block A.5(build tension: cliffhanger style idea being eluded to)
};

Transition(location change){
    Generate new location if it makes sense
    Possible description of the journey
    Description of new location, if necessary for the story development
};

Prose block B{
* Sub-block B.1(new character generated and introduced - something of their thoughts and feelings)
* Sub-block B.2(brief description of where the character is)
* Sub-block B.3(new technology introduced, describe technology in a natural way)
};

Transition(location change?){
    Possible description of the journey
    Description of new location, if necessary for the story development
};