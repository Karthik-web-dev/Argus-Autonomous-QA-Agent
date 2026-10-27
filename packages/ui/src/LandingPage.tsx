import { Nav } from "@/components/landing/Nav";
import { Hero } from "@/components/landing/Hero";
import { LogoBar } from "@/components/landing/LogoBar";
import { TaskGrid } from "@/components/landing/TaskGrid";
import { TrustSection } from "@/components/landing/TrustSection";
import { RolesSection } from "@/components/landing/RolesSection";
import { UseCases } from "@/components/landing/UseCases";
import { ConsoleSection } from "@/components/landing/ConsoleSection";
import { McpSection } from "@/components/landing/McpSection";
import { FinalCta } from "@/components/landing/FinalCta";
import { Footer } from "@/components/landing/Footer";

export default function LandingPage() {
  return (
    <main>
      <Nav />
      <Hero />
      <LogoBar />
      <TaskGrid />
      <TrustSection />
      <RolesSection />
      <UseCases />
      <ConsoleSection />
      <McpSection />
      <FinalCta />
      <Footer />
    </main>
  );
}
