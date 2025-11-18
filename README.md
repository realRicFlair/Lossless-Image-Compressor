This is a Lossless Image Compressor that I made for a class competition for CMPT 365! Decided to make it public since it was cool enough to show some friends lol.  
I used the LOCO-I Predictor and encoded the residuals using arithmetic encoding.  
Since it was based off a previous assignment, it features a custom parser for BMP files, and thus can only convert BMP files.
It compresses into the ".cmpt365" format. It achieves a pretty good compression ratio. It gets a bits per pixel slightly under the entropy of an image.  
In trials, I managed to easily get compression ratios from 3x-4x. Sometimes making the file 23% of the size of the original!  
  
It was inspired off of JPEG-LS. I found a paper for it and spent a week figuring it out: https://www.sfu.ca/~jiel/courses/861/ref/LOCOI.pdf

