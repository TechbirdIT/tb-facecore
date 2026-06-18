import { Composition } from "remotion";
import { FaceCore, TOTAL_FRAMES } from "./FaceCore";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="FaceCore"
      component={FaceCore}
      durationInFrames={TOTAL_FRAMES}
      fps={30}
      width={1920}
      height={1080}
    />
  );
};
