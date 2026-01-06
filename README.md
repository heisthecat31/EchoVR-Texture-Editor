Welcome to EchoVR texture editor, it took effort making this sadly when it was meant to take only a day. 

This program can be opened as python script or through the .exe, DO NOT OPEN echoModifyFiles.exe as it is only there to be used by the editor program and do not close the cmd which opens when extracting(cmd only shows when using the .exe version).
When opening the app it can take up to 3 minutes to load each time whilst it loads the texture files, it will also take a long time for the extraction and repacking process of the code to complete, luckily extraction is something you only have to do once, on starting the app select the data folder and the extraction folder, after it is extracted you can then select the output folder and set it as the same directory as the extraction folder, this is where the texture files will be pulled from, then input folder will be any folder you want it to be, but there will be an input folder provided which you can select.

After you find and change the texture you want you then click the repack button and wait for it to be done, when clicking the repack button it will ask for the directory you want the new package and manifest files to save to, i have left the "Saved Folders" empty so you can choose that by default. Repacking can take from 5-10 minutes depending on PC specs. Do not cancel the repacking.

After repacking is done go into the folder where the package and manifest files got repacked to and cut both the "packages" and "manifests" folders and place them into the directory the original ones are, for example .\ready-at-dawn-echo-arena\_data\5932408047\rad15\win10.

Then open the game and see your new textures. When replacing textures if the replace texture button is blanked out click on another texture then click back to the one you want to change, will fix this in next update.

ps. the config.json file saves all folder directories and allows you to change the default external editor to what you want. It is recommended to use Renderdoc.

Any questions message @he_is_the_cat on discord and special thanks to Exhibitmark for creating the original extraction tool and Goopsie for making it easier to use.
https://github.com/Exhibitmark/carnation
https://github.com/goopsie/evrFileTools


IMPORTANT --> when making your dds textures do not use a converter, instead use a photo editor and export as dds, a free online tool is https://www.photopea.com, "drag and drop, edit it then export -> more -> dds" here you can lock the resolution and change it also.

https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist?view=msvc-170#latest-supported-redistributable-version - THIS IS REQUIRED TO MAKE TEXCONV.EXE WORK.

This now works with quest standalone, download quest data from https://mia.cdn.echo.taxi/_data.zip.
<img width="1396" height="897" alt="Screenshot (205)" src="https://github.com/user-attachments/assets/81c32b3b-f92a-4752-9704-09cd30724d7e" />
