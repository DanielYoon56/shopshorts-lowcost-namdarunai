import "./index.css";
import React from "react";
import { AbsoluteFill, Composition, getInputProps, staticFile, Video } from "remotion";
import { HelloWorld, myCompSchema } from "./HelloWorld";
import { Logo, myCompSchema2 } from "./HelloWorld/Logo";
import { DynamicVideo, dynamicVideoSchema } from "./DynamicVideo";
import activeProps from "./active_props.json";

// Component to preview the final rendered MP4 directly
const RenderedVideoPreview: React.FC<{ folderName: string }> = ({ folderName }) => {
  const videoSrc = staticFile(`outputs/${folderName}/output.mp4`);
  return (
    <AbsoluteFill style={{ backgroundColor: "#000000" }}>
      <Video
        src={videoSrc}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
        }}
      />
    </AbsoluteFill>
  );
};

export const RemotionRoot: React.FC = () => {
  const inputProps = (getInputProps() || {}) as any;
  const mergedProps = {
    ...activeProps,
    ...inputProps,
    sceneData:
      inputProps.sceneData && inputProps.sceneData.length > 0
        ? inputProps.sceneData
        : activeProps.sceneData || [],
  };
  const durationInFrames = Math.max(
    1,
    inputProps.durationInFrames ||
      mergedProps.durationInFrames ||
      activeProps.durationInFrames ||
      600
  );

  return (
    <>
      <Composition
        id="DynamicVideo"
        component={DynamicVideo}
        durationInFrames={durationInFrames}
        fps={30}
        width={1080}
        height={1920}
        schema={dynamicVideoSchema}
        defaultProps={mergedProps as any}
      />

      <Composition
        id="RenderedVideoPreview"
        component={RenderedVideoPreview}
        durationInFrames={durationInFrames}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{
          folderName: mergedProps.folderName || "261109_2145",
        }}
      />

      <Composition
        // You can take the "id" to render a video:
        // npx remotion render HelloWorld
        id="HelloWorld"
        component={HelloWorld}
        durationInFrames={150}
        fps={30}
        width={1920}
        height={1080}
        // You can override these props for each render:
        // https://www.remotion.dev/docs/parametrized-rendering
        schema={myCompSchema}
        defaultProps={{
          titleText: "Welcome to Remotion",
          titleColor: "#000000",
          logoColor1: "#91EAE4",
          logoColor2: "#86A8E7",
        }}
      />

      {/* Mount any React component to make it show up in the sidebar and work on it individually! */}
      <Composition
        id="OnlyLogo"
        component={Logo}
        durationInFrames={150}
        fps={30}
        width={1920}
        height={1080}
        schema={myCompSchema2}
        defaultProps={{
          logoColor1: "#91dAE2" as const,
          logoColor2: "#86A8E7" as const,
        }}
      />
    </>
  );
};

