# example ci
Example CI is exactly as it sounds, an example of continuous integration system. It's an educational project that shows all the work that goes into a CI, and more features will be added as time goes on.

## What is CI?
Continuous integration at its core is a development practice where developers integrate code into a shared repository frequently, preferably several times a day. Each integration can then be verified by an automated build and automated tests. By doing so, you can detect errors quickly, and locate them more easily.

By automating the process of running tests, if there's ever a push to the repository that breaks the build, you'll know about it immediately. Having a timeline of what broke in which commit is very useful for discovering errors.

## How does it work?
Right now there's no automated tool to set it up, but if it's set up correctly, then it adds a post-commit hook to your git repo that, after every commit you do, it sends a copy of the commit id to an observer which then asks the CI server to build the commit. The CI server updates its clone of your git repo to the given commit id and then runs the tests. Once it's done there's a simple webpage that shows the results of the tests, and a hard txt copy that gets stored in the CI folder as well.