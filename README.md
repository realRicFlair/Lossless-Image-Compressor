This is a Lossless Image Compressor that I made for a class competition for CMPT 365! Decided to make it public since it was cool enough to show some friends lol.
I used the LOCO-I Predictor and encoded the residuals using arithmetic encoding.
It currently compresses bmp files into the ".cmpt365" format. It achieves a pretty good compression ratio. It gets a bits per pixel slightly under the entropy of an image.

It was inspired off of JPEG-LS. I found a paper for it and spent a week figuring it out: https://www.sfu.ca/~jiel/courses/861/ref/LOCOI.pdf

